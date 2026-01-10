
import os
from rich import print
try:
    from mem0 import Memory
except ImportError:
    Memory = None
    print("[yellow]⚠️ mem0 not installed. Memory features will be disabled.[/yellow]")

class MemoryStore:
    """
    Wrapper around the mem0 library for managing persistent user memories.
    Handles initialization, adding, searching, and retrieving memories.
    """

    def __init__(self, user_id="default_user", local_path=None):
        """
        Initializes the MemoryStore.

        Args:
            user_id (str, optional): The default user ID to associate with memories. Defaults to "default_user".
            local_path (str, optional): Custom path for the memory database. Defaults to None.
        """
        self.user_id = user_id
        if Memory:
            # Local mode by default if no config provided, handles ~/.mem0 internally or custom path
            config = {}
            if local_path:
                config["db_path"] = local_path
            
            self.m = Memory(config=config) if config else Memory()
            print(f"[green]🧠 Mem0 initialized for user: {user_id}[/green]")
        else:
            self.m = None

    def add(self, text: str, user_id: str = None):
        """
        Adds a new memory or fact to the store.

        Args:
            text (str): The content of the memory.
            user_id (str, optional): The user ID associated with this memory. Defaults to instance's user_id.
        """
        if not self.m: return
        target_user = user_id or self.user_id
        # mem0 .add takes messages or text.
        self.m.add(text, user_id=target_user)

    def search(self, query: str, user_id: str = None) -> list:
        """
        Searches for relevant memories based on a query string.

        Args:
            query (str): The search query.
            user_id (str, optional): The user ID to search within. Defaults to instance's user_id.

        Returns:
            list: A list of search results.
        """
        if not self.m: return []
        target_user = user_id or self.user_id
        results = self.m.search(query, user_id=target_user)
        return results

    def get_all(self, user_id: str = None) -> list:
        """
        Retrieves all stored memories for a specific user.

        Args:
            user_id (str, optional): The user ID to retrieve memories for. Defaults to instance's user_id.

        Returns:
            list: A list of all memories.
        """
        if not self.m: return []
        target_user = user_id or self.user_id
        return self.m.get_all(user_id=target_user)
