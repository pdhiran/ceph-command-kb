"""
Example integration of Ceph Command KB with Bob agents and other AI frameworks.

This module provides ready-to-use classes and functions for integrating
the Ceph Command KB REST API with various AI agent frameworks.
"""

import requests
from typing import Optional, Dict, List, Any
import json


class CephCommandKBClient:
    """
    Client for interacting with the Ceph Command KB REST API.
    
    This client provides a simple interface for Bob agents and other
    AI systems to verify Ceph commands, search the knowledge base,
    and validate test scripts.
    
    Example:
        >>> kb = CephCommandKBClient("http://localhost:9090")
        >>> result = kb.verify_command("ceph osd pool create")
        >>> if result["status"] == "VERIFIED":
        ...     print("Command is valid!")
    """
    
    def __init__(self, base_url: str = "http://localhost:9090", timeout: int = 30):
        """
        Initialize the Ceph Command KB client.
        
        Args:
            base_url: Base URL of the REST API server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._verify_connection()
    
    def _verify_connection(self) -> None:
        """Verify the server is reachable and healthy."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            response.raise_for_status()
            health = response.json()
            if not health.get("kb_loaded"):
                raise ConnectionError("Knowledge base not loaded on server")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Cannot connect to Ceph Command KB at {self.base_url}: {e}")
    
    def verify_command(
        self,
        command: str,
        flags: Optional[List[str]] = None,
        arguments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Verify a Ceph command exists and is valid.
        
        Args:
            command: The command to verify (e.g., "ceph osd pool create")
            flags: Optional list of flags to verify (e.g., ["--size", "--pg-num"])
            arguments: Optional list of arguments to verify (e.g., ["pool_name", "pg_num"])
        
        Returns:
            Dictionary with verification results including:
            - status: "VERIFIED", "NOT_VERIFIED", or "PARTIALLY_VERIFIED"
            - command_verified: bool indicating if command exists
            - flags_verified: dict of flag verification results (if flags provided)
            - arguments_verified: dict of argument verification results (if arguments provided)
        
        Example:
            >>> result = kb.verify_command(
            ...     "ceph osd pool create",
            ...     flags=["--size"],
            ... )
        """
        payload = {"command": command}
        if flags:
            payload["flags"] = flags
        if arguments:
            payload["arguments"] = arguments
        
        response = requests.post(
            f"{self.base_url}/api/verify_command",
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def search_commands(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for Ceph commands by keyword or description.
        
        Args:
            query: Search query (e.g., "nfs cluster create")
            limit: Maximum number of results to return
        
        Returns:
            Dictionary with search results including matched commands
        
        Example:
            >>> results = kb.search_commands("rbd mirror")
            >>> for cmd in results["results"]:
            ...     print(cmd["name"])
        """
        response = requests.post(
            f"{self.base_url}/api/search_commands",
            json={"query": query, "limit": limit},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def find_command(self, command_name: str) -> Dict[str, Any]:
        """
        Look up a specific command by its exact full name.
        
        Args:
            command_name: Full command name (e.g., "ceph osd pool create")
        
        Returns:
            Dictionary with command details or similar commands if not found
        
        Example:
            >>> cmd = kb.find_command("ceph osd pool create")
            >>> print(cmd["command"]["description"])
        """
        response = requests.post(
            f"{self.base_url}/api/find_command",
            json={"command_name": command_name},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def verify_config(self, name: str) -> Dict[str, Any]:
        """
        Verify a Ceph configuration parameter.
        
        Args:
            name: Config parameter name (e.g., "osd_pool_default_size")
        
        Returns:
            Dictionary with config details including type, default, and constraints
        
        Example:
            >>> config = kb.verify_config("osd_pool_default_size")
            >>> if config["status"] == "VERIFIED":
            ...     print(f"Default: {config['default']}, Type: {config['type']}")
        """
        response = requests.post(
            f"{self.base_url}/api/verify_config",
            json={"name": name},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def search_config(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search configuration parameters by name or description.
        
        Args:
            query: Search query
            limit: Maximum number of results
        
        Returns:
            Dictionary with matching config parameters
        """
        response = requests.post(
            f"{self.base_url}/api/search_config",
            json={"query": query, "limit": limit},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def review_test(self, script_content: str) -> Dict[str, Any]:
        """
        Perform a comprehensive review of a test script.
        
        This analyzes the script for:
        - Invalid commands
        - Missing cleanup operations
        - Destructive commands
        - Best practice violations
        - Duplicate commands
        
        Args:
            script_content: The test script content to review
        
        Returns:
            Dictionary with detailed review results and recommendations
        
        Example:
            >>> script = '''
            ... ceph osd pool create mypool 32
            ... rbd create img --size 1024
            ... '''
            >>> review = kb.review_test(script)
            >>> for finding in review["findings"]:
            ...     print(f"{finding['severity']}: {finding['message']}")
        """
        response = requests.post(
            f"{self.base_url}/api/review_test",
            json={"script_content": script_content},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def validate_script(self, script_content: str) -> Dict[str, Any]:
        """
        Quick validation of a script (faster than review_test).
        
        Args:
            script_content: The script content to validate
        
        Returns:
            Dictionary with validation results
        """
        response = requests.post(
            f"{self.base_url}/api/validate_script",
            json={"script_content": script_content},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def list_subcommands(self, command_prefix: str) -> Dict[str, Any]:
        """
        List all subcommands under a command prefix.
        
        Args:
            command_prefix: Command prefix (e.g., "ceph osd")
        
        Returns:
            Dictionary with list of subcommands
        
        Example:
            >>> subcmds = kb.list_subcommands("ceph osd pool")
            >>> for cmd in subcmds["subcommands"]:
            ...     print(cmd)
        """
        response = requests.post(
            f"{self.base_url}/api/list_subcommands",
            json={"command_prefix": command_prefix},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def get_help(self, command_name: str) -> Dict[str, Any]:
        """
        Get parsed help metadata for a command.
        
        Args:
            command_name: Full command name
        
        Returns:
            Dictionary with parsed help information
        """
        response = requests.post(
            f"{self.base_url}/api/get_help",
            json={"command_name": command_name},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check the health status of the KB server.
        
        Returns:
            Dictionary with health status and statistics
        """
        response = requests.get(f"{self.base_url}/health", timeout=5)
        response.raise_for_status()
        return response.json()


# LangChain Integration
def create_langchain_tools(kb_url: str = "http://localhost:9090"):
    """
    Create LangChain tools for Ceph Command KB integration.
    
    Args:
        kb_url: Base URL of the Ceph Command KB REST API
    
    Returns:
        List of LangChain Tool objects
    
    Example:
        >>> from langchain.agents import initialize_agent, AgentType
        >>> from langchain.llms import OpenAI
        >>> 
        >>> tools = create_langchain_tools()
        >>> llm = OpenAI(temperature=0)
        >>> agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
        >>> result = agent.run("Find commands for creating RBD images")
    """
    try:
        from langchain.tools import Tool
    except ImportError:
        raise ImportError("langchain not installed. Install with: pip install langchain")
    
    kb = CephCommandKBClient(kb_url)
    
    def verify_command_wrapper(command: str) -> str:
        """Verify a Ceph command."""
        result = kb.verify_command(command)
        return json.dumps(result, indent=2)
    
    def search_commands_wrapper(query: str) -> str:
        """Search for Ceph commands."""
        result = kb.search_commands(query, limit=10)
        return json.dumps(result, indent=2)
    
    def verify_config_wrapper(name: str) -> str:
        """Verify a Ceph config parameter."""
        result = kb.verify_config(name)
        return json.dumps(result, indent=2)
    
    def review_test_wrapper(script: str) -> str:
        """Review a Ceph test script."""
        result = kb.review_test(script)
        return json.dumps(result, indent=2)
    
    tools = [
        Tool(
            name="VerifyCephCommand",
            func=verify_command_wrapper,
            description=(
                "Verify a Ceph command exists and is valid. "
                "Input should be the full command string (e.g., 'ceph osd pool create'). "
                "Returns validation results with any issues found."
            )
        ),
        Tool(
            name="SearchCephCommands",
            func=search_commands_wrapper,
            description=(
                "Search for Ceph commands by keyword or description. "
                "Input should be a search query (e.g., 'nfs cluster' or 'rbd mirror'). "
                "Returns a list of matching commands with descriptions."
            )
        ),
        Tool(
            name="VerifyCephConfig",
            func=verify_config_wrapper,
            description=(
                "Verify a Ceph configuration parameter. "
                "Input should be the config parameter name (e.g., 'osd_pool_default_size'). "
                "Returns type, default value, and valid range."
            )
        ),
        Tool(
            name="ReviewCephTest",
            func=review_test_wrapper,
            description=(
                "Review a Ceph test script for issues. "
                "Input should be the complete script content. "
                "Returns detailed analysis including invalid commands, missing cleanup, and risks."
            )
        )
    ]
    
    return tools


# CrewAI Integration
def create_crewai_tools(kb_url: str = "http://localhost:9090"):
    """
    Create CrewAI tools for Ceph Command KB integration.
    
    Args:
        kb_url: Base URL of the Ceph Command KB REST API
    
    Returns:
        List of CrewAI tool functions
    
    Example:
        >>> from crewai import Agent, Task, Crew
        >>> 
        >>> tools = create_crewai_tools()
        >>> agent = Agent(
        ...     role='Ceph Expert',
        ...     goal='Generate valid Ceph automation',
        ...     tools=tools
        ... )
    """
    try:
        from crewai_tools import tool
    except ImportError:
        raise ImportError("crewai-tools not installed. Install with: pip install crewai-tools")
    
    kb = CephCommandKBClient(kb_url)
    
    @tool("Verify Ceph Command")
    def verify_ceph_command(command: str) -> str:
        """
        Verify a Ceph command against the knowledge base.
        
        Args:
            command: The Ceph command to verify
        
        Returns:
            JSON string with verification results
        """
        result = kb.verify_command(command)
        return json.dumps(result, indent=2)
    
    @tool("Search Ceph Commands")
    def search_ceph_commands(query: str) -> str:
        """
        Search for Ceph commands by keyword.
        
        Args:
            query: Search query
        
        Returns:
            JSON string with matching commands
        """
        result = kb.search_commands(query, limit=10)
        return json.dumps(result, indent=2)
    
    @tool("Review Ceph Test Script")
    def review_ceph_test(script: str) -> str:
        """
        Review a Ceph test script for issues and best practices.
        
        Args:
            script: The test script content
        
        Returns:
            JSON string with detailed review
        """
        result = kb.review_test(script)
        return json.dumps(result, indent=2)
    
    @tool("Verify Ceph Config")
    def verify_ceph_config(name: str) -> str:
        """
        Verify a Ceph configuration parameter.
        
        Args:
            name: Config parameter name
        
        Returns:
            JSON string with config details
        """
        result = kb.verify_config(name)
        return json.dumps(result, indent=2)
    
    return [
        verify_ceph_command,
        search_ceph_commands,
        review_ceph_test,
        verify_ceph_config
    ]


# Example usage for Bob agents
def bob_agent_example():
    """
    Example of using Ceph Command KB with a Bob agent workflow.
    
    This demonstrates a typical workflow where Bob:
    1. Searches for relevant commands
    2. Verifies command syntax
    3. Generates a script
    4. Reviews the script for issues
    """
    kb = CephCommandKBClient()
    
    # Step 1: Search for commands
    print("Step 1: Searching for NFS cluster commands...")
    search_results = kb.search_commands("nfs cluster create")
    print(f"Found {search_results.get('total_results', 0)} commands")
    
    # Step 2: Verify specific command
    print("\nStep 2: Verifying command syntax...")
    command = "ceph nfs cluster create"
    verify_result = kb.verify_command(command)
    
    if verify_result.get("status") == "VERIFIED":
        print(f"  Command '{command}' is valid")
    else:
        print(f"  Command '{command}' status: {verify_result.get('status')}")
        if verify_result.get("similar_commands"):
            print(f"  Similar: {verify_result['similar_commands']}")
    
    # Step 3: Generate a test script (simulated)
    test_script = """
    # Create NFS cluster
    ceph nfs cluster create mynfs
    
    # Create NFS export
    ceph nfs export create cephfs mynfs /export /data
    
    # List exports
    ceph nfs export ls mynfs
    """
    
    # Step 4: Review the script
    print("\nStep 4: Reviewing test script...")
    review = kb.review_test(test_script)
    
    print(f"Review complete:")
    print(f"  - Commands found: {review.get('total_commands', 0)}")
    print(f"  - Verified: {review.get('verified_commands', 0)}")
    print(f"  - Findings: {len(review.get('findings', []))}")
    
    if review.get("findings"):
        print("\nFindings:")
        for finding in review["findings"]:
            print(f"  [{finding.get('severity', 'info')}] {finding.get('message', '')}")
    
    # Step 5: Check config parameter
    print("\nStep 5: Checking config parameter...")
    config = kb.verify_config("osd_pool_default_size")
    if config.get("status") == "VERIFIED":
        print(f"  Config 'osd_pool_default_size' found")
        print(f"  Type: {config.get('type')}")
        print(f"  Default: {config.get('default')}")
    
    return {
        "search_results": search_results,
        "verify_result": verify_result,
        "review": review,
        "config": config
    }


if __name__ == "__main__":
    # Run the example
    print("=" * 60)
    print("Ceph Command KB - Bob Agent Integration Example")
    print("=" * 60)
    
    try:
        results = bob_agent_example()
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)
    except ConnectionError as e:
        print(f"\nError: {e}")
        print("\nMake sure the Ceph Command KB REST API is running:")
        print("  python -m ceph_command_kb.server.rest_api")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
