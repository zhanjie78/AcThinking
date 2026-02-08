from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from mud_battle_bot.duel import DuelService
from mud_battle_bot.engine import BattleEngine, SkillConfigError, get_status_text, load_skills
from mud_battle_bot.storage import SQLiteBattleRepository

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = (
    "可用命令：\n"
    "/start - 初始化用户并开始一局\n"
    "/new - 重开一局\n"
    "/fight - 查看新的双人出招方式\n"
    "/status - 查看双方状态\n"
    "/seed <int> - 设置或查看当前随机种子\n"
    "/help - 查看帮助\n"
    "发送 `开始回合.干` 或 `.干` 提交本回合动作"
)

START_TEXT = (
    "欢迎来到回合制战斗机器人！\n"
    "你将与 AI 进行 1v1 对战。\n"
    "每次 /fight 会执行：回合开始 -> 玩家行动 -> AI行动 -> DOT结算 -> 胜负判断。\n"
    "状态包含中毒/沉默/护盾，记得观察 CD 和异常状态。\n"
    "输入 /fight 开始战斗，或 /help 查看指令。"
)


class BotRuntime:
    def __init__(self) -> None:
        skills = load_skills()
        self.engine = BattleEngine(skills)
        self.duel = DuelService(self.engine)
        self.repo = SQLiteBattleRepository()
        self.fight_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


RUNTIME: BotRuntime | None = None


def get_runtime() -> BotRuntime:
    global RUNTIME
    if RUNTIME is None:
        RUNTIME = BotRuntime()
    return RUNTIME


def _mention_html(update: Update) -> str:
    user = update.effective_user
    if user is None:
        return "@unknown"
    shown_name = user.username or user.full_name or str(user.id)
    return f'<a href="tg://user?id={user.id}">@{shown_name}</a>'


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    runtime = get_runtime()
    battle = runtime.engine.create_new_battle(chat_id)
    runtime.repo.save_battle(chat_id, battle)
    await update.message.reply_text(f"{START_TEXT}\n\n已为你创建新战斗。")


async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    runtime = get_runtime()
    old_battle = runtime.repo.load_battle(chat_id)
    seed = old_battle.seed if old_battle else None
    debug_mode = old_battle.debug_mode if old_battle else False
    battle = runtime.engine.create_new_battle(chat_id, seed=seed)
    battle.debug_mode = debug_mode
    runtime.repo.save_battle(chat_id, battle)
    await update.message.reply_text("新战斗已创建，双方状态已重置。输入 `开始回合.干` 开打！", parse_mode=ParseMode.MARKDOWN)


async def fight_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text("现在改为双人同步出招：双方各发送 `开始回合.干`（或 `.干`）后才会统一结算。", parse_mode=ParseMode.MARKDOWN)


async def action_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or update.effective_user is None:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    runtime = get_runtime()

    async with runtime.fight_locks[chat_id]:
        battle = runtime.repo.load_battle(chat_id)
        if battle is None:
            await update.message.reply_text("你还没有战斗记录，请先发送 /start 初始化。")
            return

        mention = _mention_html(update)
        result = runtime.duel.submit_action(battle, user_id=user_id, mention_html=mention)
        runtime.repo.save_battle(chat_id, battle)

    await update.message.reply_text(result.message, parse_mode=ParseMode.HTML)
    if result.round_report:
        await update.message.reply_text(result.round_report)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    runtime = get_runtime()
    battle = runtime.repo.load_battle(chat_id)
    if battle is None:
        await update.message.reply_text("你还没有战斗记录，请先发送 /start 初始化。")
        return

    await update.message.reply_text(get_status_text(battle, runtime.engine.skills))


async def seed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    runtime = get_runtime()
    battle = runtime.repo.load_battle(chat_id)
    if battle is None:
        await update.message.reply_text("你还没有战斗记录，请先发送 /start 初始化。")
        return

    if not context.args:
        if battle.seed is None:
            await update.message.reply_text("当前未设置seed（使用系统随机）。")
        else:
            await update.message.reply_text(f"当前seed：{battle.seed}")
        return

    try:
        seed = int(context.args[0])
    except ValueError:
        await update.message.reply_text("seed 必须是整数，例如：/seed 42")
        return

    runtime.engine.set_seed(battle, seed)
    battle.debug_mode = True
    runtime.repo.save_battle(chat_id, battle)
    await update.message.reply_text(f"已设置seed：{seed}（已开启调试seed显示）")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception in Telegram handler", exc_info=context.error)
    if isinstance(update, Update) and update.message is not None:
        await update.message.reply_text("系统开小差了，请稍后再试。")


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("new", new_cmd))
    application.add_handler(CommandHandler("fight", fight_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("seed", seed_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^(开始回合)?\.干$"), action_cmd))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("环境变量 TELEGRAM_BOT_TOKEN 未设置。")

    try:
        get_runtime()
    except SkillConfigError:
        logger.exception("技能配置加载失败，机器人无法启动")
        raise

    app = build_application(token)
    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
