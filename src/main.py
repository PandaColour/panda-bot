"""
Panda Bot - 通用智能体

入口文件
"""
from src.agent import Agent
from src.config import ConfigManager
from src.session import Session
from src.utils import get_logger, setup_logging


def main():
    """主入口 - 多轮对话循环"""
    # 初始化日志系统
    setup_logging("DEBUG")

    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")

    config = ConfigManager()
    session = Session()  # 外层创建，维护整个对话历史

    logger.info(f"会话目录: {session.work_dir}")

    print("Panda Bot - 输入 'exit' 或 'quit' 退出\n")

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            logger.info("用户中断程序")
            print("\n再见!")
            break

        if not user_input.strip():
            continue

        if user_input.lower() in ["exit", "quit"]:
            logger.info("用户请求退出")
            print("再见!")
            break

        logger.debug(f"用户输入: {user_input}")

        # 保存用户输入到 session
        session.add_user_input(user_input)

        # 创建 Agent 处理当前任务
        logger.info("开始处理任务...")
        agent = Agent(session, config)
        result = agent.run()
        logger.info(f"任务完成，结果长度: {len(result)}")

        # 保存 Agent 响应到 session
        session.add_agent_response(result)

        print(f"\n{result}\n")


if __name__ == "__main__":
    main()
