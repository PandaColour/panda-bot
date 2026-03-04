"""
Panda Bot - 通用智能体

入口文件
"""
from src.agent import Agent
from src.config import ConfigManager
from src.session import Session


def main():
    """主入口 - 多轮对话循环"""
    config = ConfigManager()
    session = Session()  # 外层创建，维护整个对话历史

    print("Panda Bot - 输入 'exit' 或 'quit' 退出\n")

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not user_input.strip():
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("再见!")
            break

        # 保存用户输入到 session
        session.add_user_input(user_input)

        # 创建 Agent 处理当前任务
        agent = Agent(session, config)
        result = agent.run()

        # 保存 Agent 响应到 session
        session.add_agent_response(result)

        print(f"\n{result}\n")


if __name__ == "__main__":
    main()
