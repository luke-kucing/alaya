import logging

from fastmcp import FastMCP

from alaya.config import get_vault_root, ConfigError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        raise SystemExit(1)

    logger.info("alaya starting — vault root: %s", vault_root)

    from alaya.index.store import get_store
    from alaya.watcher import start_watcher

    store = get_store(vault_root)
    observer = start_watcher(vault_root, store)
    logger.info("File watcher started")

    try:
        mcp.run()
    finally:
        observer.stop()
        observer.join()
        logger.info("File watcher stopped")


if __name__ == "__main__":
    main()
