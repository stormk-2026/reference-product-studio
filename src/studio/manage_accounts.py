"""Private server CLI. Never accepts passwords in command-line arguments."""

import argparse
import getpass
from pathlib import Path

from studio.config import data_dir
from studio.services.accounts import Accounts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-owner-file", type=Path)
    parser.add_argument("--reset-password", metavar="USERNAME")
    args = parser.parse_args()
    accounts = Accounts(data_dir())
    if args.bootstrap_owner_file:
        if any(u["owner"] for u in accounts.users()):
            print("主账户已存在；未修改密码。")
            return
        username, password = args.bootstrap_owner_file.read_text().splitlines()[:2]
        accounts.create(username, password, owner=True)
        print("主账户已创建；原作品归主账户所有。")
    elif args.reset_password:
        password = getpass.getpass("新密码（不回显）：")
        if password != getpass.getpass("再次输入："):
            raise SystemExit("两次密码不同")
        accounts.reset_password(args.reset_password, password)
        print("密码已更新，所有旧会话已退出。")
    else:
        parser.error("请选择初始化主账户或重置密码")


if __name__ == "__main__":
    main()
