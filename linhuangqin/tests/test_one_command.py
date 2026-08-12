"""测试 one_command.py 一键部署流程 (物流风控系统)."""
import sys
from pathlib import Path

# 确保项目根在 sys.path (模拟手动跑的情形)
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from unittest.mock import patch, MagicMock
import pytest


class TestOneCommand:
    """一键部署脚本测试."""

    def test_imports_no_error(self):
        """验证 one_command.py 可以正常 import."""
        import scripts.one_command as oc
        assert oc is not None
        assert hasattr(oc, "main")

    @pytest.mark.asyncio
    async def test_main_flow_without_train(self):
        """验证 --no-train 流程不报错 (mock _impl 层)."""
        from scripts.one_command import main

        # Mock 所有底层调用
        with (
            patch("scripts.one_command.init_db") as mock_init,
            patch("scripts.one_command.gen_data") as mock_gen,
            patch("scripts.one_command.gen_risky") as mock_risky,
            patch("scripts.one_command.train_model") as mock_train,
            patch(
                "scripts.one_command.async_engine",
                MagicMock(),
            ),
            patch(
                "scripts.one_command.text",
                MagicMock(),
            ),
        ):
            # 模拟命令行参数: --no-train
            with patch.object(sys, "argv", ["one_command.py", "--no-train"]):
                main()

            mock_init.assert_called_once()
            mock_gen.assert_called_once()
            mock_risky.assert_called_once()
            mock_train.assert_not_called()  # --no-train 不训练

    def test_argparse_defaults(self):
        """验证默认参数：count=200, risky=30."""
        from scripts.one_command import parser

        args = parser.parse_args([])
        assert args.count == 200
        assert args.risky == 30
        assert args.no_train is False
        assert args.reset is False

    def test_argparse_reset(self):
        """验证 --reset 参数."""
        from scripts.one_command import parser

        args = parser.parse_args(["--reset"])
        assert args.reset is True

    def test_argparse_custom_count(self):
        """验证自定义 --count."""
        from scripts.one_command import parser

        args = parser.parse_args(["--count", "500"])
        assert args.count == 500

    @pytest.mark.asyncio
    async def test_main_flow_full(self):
        """验证完整流程 (含训练) 的参数传递."""
        from scripts.one_command import main

        with (
            patch("scripts.one_command.init_db") as mock_init,
            patch("scripts.one_command.gen_data") as mock_gen,
            patch("scripts.one_command.gen_risky") as mock_risky,
            patch("scripts.one_command.train_model") as mock_train,
            patch(
                "scripts.one_command.async_engine",
                MagicMock(),
            ),
            patch(
                "scripts.one_command.text",
                MagicMock(),
            ),
        ):
            with patch.object(
                sys, "argv", ["one_command.py", "--count", "500", "--risky", "50"]
            ):
                main()

            mock_init.assert_called_once()
            mock_gen.assert_called_once_with(count=500, reset=False)
            mock_risky.assert_called_once_with(count=50)
            mock_train.assert_called_once_with(limit=1000)