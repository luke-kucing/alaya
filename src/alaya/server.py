from fastmcp import FastMCP

from alaya.config import get_vault_root, ConfigError

mcp = FastMCP(
    name="alaya",
    instructions=(
        "You are connected to a zk-managed personal knowledge vault. "
        "Use the available tools to read, write, search, and organize notes. "
        "Always confirm before moving, renaming, deleting, or bulk-modifying notes. "
        "Capture is always safe — no confirmation needed for append or inbox operations."
    ),
)

# tools are registered by importing their modules
import alaya.tools.read      # noqa: F401, E402
import alaya.tools.write     # noqa: F401, E402
import alaya.tools.inbox     # noqa: F401, E402
import alaya.tools.search    # noqa: F401, E402
import alaya.tools.structure # noqa: F401, E402
import alaya.tools.edit      # noqa: F401, E402
import alaya.tools.tasks     # noqa: F401, E402
import alaya.tools.gitlab    # noqa: F401, E402
import alaya.tools.ingest    # noqa: F401, E402


def main() -> None:
    try:
        vault_root = get_vault_root()
        print(f"alaya: vault root = {vault_root}")
    except ConfigError as e:
        print(f"alaya: configuration error — {e}")
        raise SystemExit(1)

    mcp.run()


if __name__ == "__main__":
    main()
