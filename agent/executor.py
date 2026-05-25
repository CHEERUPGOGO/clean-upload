"""Task Executor Module.
This module orchestrates the multi-round execution of tasks using multiple MCP servers.
It handles planning, tool execution, state management, and result synthesis.

Classes:
    TaskExecutor: Main executor for multi-round task execution
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
import json
from llm.provider import LLMProvider
from mcp_modules.server_manager_persistent import PersistentMultiServerManager as MultiServerManager
from mcp_modules.connector import MCPConnector
from agent.execution_context import ExecutionContext
import config.config_loader as config_loader
from utils.error_handler import handle_errors

from agent.examples import EXAMPLES

logger = logging.getLogger(__name__)

class TaskExecutor:
    """Orchestrates multi-round execution of tasks using multiple MCP servers.
    This class manages the execution lifecycle of complex tasks that may require
    multiple rounds of tool calls across different servers. It handles planning,
    execution, state management, and result synthesis.
    
    Attributes:
        llm: LLM provider for task planning and synthesis
        server_manager: Manager for MCP server connections
        all_tools: Dictionary of all available tools from servers
        concurrent_summarization: Whether to summarize results concurrently
        execution_results: List of all execution results
        accumulated_information: Accumulated information from all rounds
        _last_planning_info: Information about the last planning round
        
    Example:
        >>> executor = TaskExecutor(llm_provider, server_manager)
        >>> result = await executor.execute("Find weather in Tokyo")
    """

    def __init__(
        self, 
        llm_provider: LLMProvider, 
        server_manager: MultiServerManager, 
        concurrent_summarization: bool = False,
        single_round_mode: bool = False,
        serial_mode: bool = False,
    ) -> None:
        self.llm = llm_provider
        self.server_manager = server_manager
        self.all_tools = server_manager.all_tools
        self.concurrent_summarization = concurrent_summarization
        self.single_round_mode = single_round_mode
        self.serial_mode = serial_mode
        self.execution_results: List[Dict[str, Any]] = []
        self.accumulated_information = ""
        # Keep uncompressed version for judge evaluation
        self.accumulated_information_uncompressed = ""
        # Compact, structured state used only for subsequent planning prompts
        self.planning_state: List[Dict[str, Any]] = []
        self._planning_item_ref_limit = 5
        self._planning_text_limit = 240
        self._last_planning_info: Optional[Dict[str, Any]] = None
        
        # Planning JSON compliance tracking
        self._total_planned_tools = 0
        self._valid_planned_tools = 0
        
        # Token usage tracking
        self.total_output_tokens = 0
        self.total_prompt_tokens = 0
        self.total_tokens = 0
        
        # Prompt tracking
        self.prompts_history = []
        
        # Tool calls tracking - store simplified tool call information
        self.tool_calls_history = []

        # Candidate bus: stores concrete entity IDs extracted from each round's
        # tool results so that subsequent serial rounds can directly reference them.
        # Structure: list of dicts, each with round, tool, and extracted key-value pairs.
        self.candidate_bus: List[Dict[str, Any]] = []

        # Load ICLR fewshot in context learning examples
        self.examples = EXAMPLES

    async def execute(self, task: str) -> Dict[str, Any]:
        """Execute a task through multiple rounds of planning and tool calls.
        
        This is the main entry point for task execution. It manages the multi-round
        execution loop, calling tools as needed and accumulating information until
        the task is complete.
        
        Args:
            task: Natural language description of the task to execute
            
        Returns:
            Dictionary containing:
                - solution: Final synthesized solution
                - total_rounds: Number of execution rounds
                - execution_results: List of all tool execution results
                - planning_json_compliance: Ratio of valid to total planned tools
                - accumulated_information: All gathered information
                
        Raises:
            RuntimeError: If execution fails after maximum rounds
        """
        if self.single_round_mode:
            return await self._execute_single_round(task)
        
        logger.info(f"Starting multi-server execution for task: \"{task}\"")
        
        # Log token consumption statistics for tool descriptions and input schemas
        self._log_tools_token_stats()
        
        
        self._last_planning_info = {
            'mode': 'multi-round',
            'rounds': []
        }
        
        max_rounds = config_loader.get_max_execution_rounds()
        actual_rounds_executed = 0  # Track actual rounds that executed tools
        
        for round_num in range(1, max_rounds + 1):
            logger.info(f"--- Starting Round {round_num}/{max_rounds} ---")

            should_continue, reasoning, round_executions = await self._plan_next_actions(task, round_num)
            
            round_planning_info = {
                'round_number': round_num,
                'should_continue': should_continue,
                'reasoning': reasoning
            }
            self._last_planning_info['rounds'].append(round_planning_info)
            
            logger.info(f"Decision: {'CONTINUE' if should_continue else 'STOP'}. Reasoning: {reasoning}")

            if not should_continue:
                logger.info(f"Stopping execution after {actual_rounds_executed} rounds.")
                break

            if not round_executions:
                logger.info(f"No tool executions planned for round {round_num}. Stopping.")
                break

            logger.info(f"Round {round_num}: executing {len(round_executions)} tool(s) in parallel")
            round_results = await self._execute_planned_tools(round_executions, round_num)
            await self._update_state(round_results, round_num)
            actual_rounds_executed += 1  # Increment only after tools are executed

        final_solution = await self._synthesize_final_solution(task, len(self.execution_results))
        logger.info("Multi-server execution finished.")
        
        # Calculate planning JSON compliance
        planning_json_compliance = (self._valid_planned_tools / self._total_planned_tools) if self._total_planned_tools > 0 else 1.0
        
        logger.info(f"Planning JSON Compliance: {self._valid_planned_tools}/{self._total_planned_tools} = {planning_json_compliance:.2%}")
        
        return {
            "solution": final_solution,
            "total_rounds": actual_rounds_executed,
            "execution_results": self.execution_results,
            "planning_json_compliance": planning_json_compliance,
            "accumulated_information": self.accumulated_information,
            # Compact prompt-facing state kept separate from judge-facing execution history
            "planning_state": self.planning_state,
            # Include uncompressed version for judge evaluation
            "accumulated_information_uncompressed": self.accumulated_information_uncompressed,
            # Token usage statistics
            "total_output_tokens": self.total_output_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_tokens": self.total_tokens,
            # Tool calls history - simplified version for tracking
            "tool_calls_history": self.tool_calls_history,
            # Candidate bus - concrete entity IDs from each round
            "candidate_bus": self.candidate_bus,
            # Prompt history for debugging
            "prompts_history": self.prompts_history
        }

    async def _execute_single_round(self, task: str) -> Dict[str, Any]:
        """Execute a task with single round planning only.
        
        This simplified mode does:
        1. One planning round to determine which tools to call
        2. Execute all planned tools in parallel
        3. Return results without synthesizing final solution
        
        Args:
            task: Natural language description of the task to execute
            
        Returns:
            Dictionary containing:
                - solution: Planning decision and tool execution results (not synthesized)
                - total_rounds: Always 1
                - execution_results: List of tool execution results
                - planning_json_compliance: Ratio of valid to total planned tools
                - accumulated_information: Tool execution results
        """
        logger.info(f"[SINGLE-ROUND MODE] Starting execution for task: \"{task}\"")
        
        # Log tool statistics
        self._log_tools_token_stats()
        
        self._last_planning_info = {
            'mode': 'single-round',
            'rounds': []
        }
        
        # Single planning round
        round_num = 1
        logger.info(f"--- Single Round Planning ---")
        
        should_continue, reasoning, round_executions = await self._plan_next_actions(task, round_num)
        
        round_planning_info = {
            'round_number': round_num,
            'should_continue': should_continue,
            'reasoning': reasoning
        }
        self._last_planning_info['rounds'].append(round_planning_info)
        
        logger.info(f"Planning Decision: {reasoning}")
        logger.info(f"Planned {len(round_executions)} tool calls")
        
        # Execute planned tools
        if round_executions:
            logger.info(f"[SINGLE-ROUND MODE] Executing {len(round_executions)} tool(s) in parallel")
            round_results = await self._execute_planned_tools(round_executions, round_num)
            await self._update_state(round_results, round_num)
        else:
            logger.info("No tools planned for execution")
        
        # Calculate planning JSON compliance
        planning_json_compliance = (self._valid_planned_tools / self._total_planned_tools) if self._total_planned_tools > 0 else 1.0
        
        logger.info(f"Planning JSON Compliance: {self._valid_planned_tools}/{self._total_planned_tools} = {planning_json_compliance:.2%}")
        
        # Build simple solution summary (no LLM synthesis)
        solution_parts = [
            f"[SINGLE-ROUND MODE] Planning: {reasoning}",
            f"\nExecuted {len(self.execution_results)} tool(s)",
        ]
        
        if self.accumulated_information:
            solution_parts.append(f"\nResults Summary:\n{self.accumulated_information}")
        
        simple_solution = "\n".join(solution_parts)
        
        logger.info("[SINGLE-ROUND MODE] Execution finished.")
        
        return {
            "solution": simple_solution,
            "total_rounds": 1,
            "execution_results": self.execution_results,
            "planning_json_compliance": planning_json_compliance,
            "accumulated_information": self.accumulated_information,
            "planning_state": self.planning_state,
            "accumulated_information_uncompressed": self.accumulated_information_uncompressed,
            # Token usage statistics
            "total_output_tokens": self.total_output_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_tokens": self.total_tokens,
            # Tool calls history
            "tool_calls_history": self.tool_calls_history
        }

    # Per-item metadata fields worth propagating through the candidate bus.
    # These let the planner see scores, ranks, ratings, sentiment, etc.
    # without bloating the main accumulated_information / planning_state.
    _BUS_ITEM_FIELDS = {
        'score', 'rank', 'hit_rate', 'matching_words', 'similarity_score',
        'average_rating', 'rating_number', 'rating', 'price',
        'title', 'name', 'brand', 'category', 'main_category',
        'positive', 'negative', 'total', 'positive_rate',
        'matched_opinions', 'matched_summaries',
        'error',
    }

    def _extract_bus_entries_from_result(self, result: Dict[str, Any], round_num: int) -> None:
        """Extract concrete entity IDs and key metadata from a tool result
        and append to candidate_bus.

        Uses *result_raw* (the full, unsimplified server response) when
        available so that downstream serial rounds can access scores, ranks,
ratings, sentiment percentages, etc. ?all without bloating the
        planning-state prompt with full item details.
        """
        tool_name = result.get('tool', 'unknown')
        if not result.get('success'):
            return

        # Prefer raw (unsimplified) result for richer extraction
        raw = result.get('result_raw') or result.get('result', '')
        if not raw:
            return

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return

        entry: Dict[str, Any] = {
            'round': round_num,
            'tool': tool_name,
        }

        # --- Flat scalar fields that are commonly needed downstream ---
        id_field_names = [
            'user_id', 'asin', 'fsq_id', 'business_id', 'venue_id',
            'item_id', 'place_id', 'product_id', 'id',
            'title', 'name', 'brand', 'category', 'main_category',
            'average_rating', 'rating_number', 'rating', 'price',
        ]
        if isinstance(data, dict):
            for key in id_field_names:
                val = data.get(key)
                if val not in (None, '', [], {}):
                    entry[key] = val

            # --- Nested dict extraction (e.g. get_item_details returns {item_id, item: {...}}) ---
            # Promote scalar fields from well-known nested dict keys into the bus entry.
            nested_dict_keys = ['item', 'venue', 'business', 'place', 'product', 'details']
            for nk in nested_dict_keys:
                nested = data.get(nk)
                if not isinstance(nested, dict):
                    continue
                for key in id_field_names:
                    if key in entry:
                        continue  # don't overwrite top-level values
                    val = nested.get(key)
                    if val not in (None, '', [], {}):
                        # Truncate long strings
                        if isinstance(val, str) and len(val) > 150:
                            val = val[:150] + '...'
                        entry[key] = val
                break  # only process the first matching nested dict

        # --- List-of-items extraction with per-item metadata ---
        list_id_keys = ['asin', 'fsq_id', 'business_id', 'venue_id', 'item_id', 'id']
        list_container_keys = [
            'items', 'results', 'businesses', 'places', 'products',
            'data', 'entries', 'rows', 'records', 'asins',
        ]

        def _extract_items_with_metadata(items_list: list, top_k: int = 10) -> list:
            """From a list of dicts, extract primary ID + key metadata per item."""
            extracted = []
            for item in items_list[:top_k]:
                if isinstance(item, str):
                    extracted.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                # Find primary ID
                item_entry: Dict[str, Any] = {}
                for ik in list_id_keys:
                    v = item.get(ik)
                    if v not in (None, ''):
                        item_entry[ik] = v
                        break
                # Attach key metadata fields
                for field in self._BUS_ITEM_FIELDS:
                    fval = item.get(field)
                    if fval is None or fval == '' or fval == []:
                        continue
                    # Truncate long strings / lists to keep bus compact
                    if isinstance(fval, str) and len(fval) > 120:
                        fval = fval[:120] + '...'
                    elif isinstance(fval, list) and len(fval) > 5:
                        fval = fval[:5]
                    item_entry[field] = fval
                if item_entry:
                    extracted.append(item_entry)
            return extracted

        if isinstance(data, dict):
            for lk in list_container_keys:
                lst = data.get(lk)
                if not isinstance(lst, list) or not lst:
                    continue
                enriched = _extract_items_with_metadata(lst)
                if enriched:
                    entry[f'{lk}_items'] = enriched
                    entry[f'{lk}_count'] = len(lst)
                    break  # Only one list per result
        elif isinstance(data, list):
            enriched = _extract_items_with_metadata(data)
            if enriched:
                entry['items_items'] = enriched
                entry['items_count'] = len(data)

        # Only append if we extracted something beyond round/tool
        if len(entry) > 2:
            self.candidate_bus.append(entry)

    def _render_candidate_bus(self) -> str:
        """Render candidate_bus into a prompt-friendly string.
        
        For entries that contain per-item metadata lists (e.g. items_items),
        renders each item as a compact one-liner so the planner can see
        scores, ranks, ratings, etc. without an unwieldy JSON blob.
        """
        if not self.candidate_bus:
            return ''
        lines = ['CANDIDATE BUS (concrete values extracted from previous rounds):']
        for entry in self.candidate_bus:
            round_num = entry.get('round', '?')
            tool = entry.get('tool', 'unknown')
            scalar_parts = []
            item_lines = []
            for k, v in entry.items():
                if k in ('round', 'tool'):
                    continue
                # Detect per-item metadata lists (xxx_items keys)
                if k.endswith('_items') and isinstance(v, list) and v and isinstance(v[0], dict):
                    # Render each item dict as a compact one-liner
                    for idx, item_dict in enumerate(v[:10]):
                        compact = ", ".join(
                            f"{ik}={json.dumps(iv, ensure_ascii=False)}"
                            for ik, iv in item_dict.items()
                        )
                        item_lines.append(f'      [{idx+1}] {compact}')
                    if len(v) > 10:
                        item_lines.append(f'      ... and {len(v)-10} more items')
                elif isinstance(v, list) and len(v) > 20:
                    scalar_parts.append(f'{k}={v[:20]}...({len(v)} total)')
                else:
                    scalar_parts.append(f'{k}={json.dumps(v, ensure_ascii=False)}')
            header = f'  Round {round_num} [{tool}]'
            if scalar_parts:
                header += f': {", ".join(scalar_parts)}'
            lines.append(header)
            if item_lines:
                lines.extend(item_lines)
        return '\n'.join(lines)

    def _build_execution_summary(self) -> str:
        """Build compact execution summary for planning prompts."""
        if self.planning_state:
            return f"\nPLANNING STATE:\n{self._render_planning_state()}\n"
        if self.execution_results:
            return "\nPLANNING STATE:\nNo reusable planning state yet.\n"
        return "\nThis is the first round - no previous execution results."

    def _render_planning_state(self) -> str:
        """Render structured planning state into a compact prompt-friendly string."""
        return self._render_planning_state_entries(self.planning_state) if self.planning_state else 'No information gathered yet.'

    def _render_planning_state_entries(self, entries: List[Dict[str, Any]]) -> str:
        lines = []
        for entry in entries:
            if entry.get("type") == "compressed_history":
                lines.append(f"- [Compressed earlier history] {entry.get('summary_text', '')}")
                continue
            lines.append(self._format_planning_state_entry(entry))
        return "\n".join(lines) if lines else 'No information gathered yet.'

    def _format_planning_state_entry(self, entry: Dict[str, Any]) -> str:
        round_num = entry.get('round', '?')
        tool_name = entry.get('tool', 'unknown')
        server = entry.get('server', 'unknown')
        status = 'SUCCESS' if entry.get('success') else 'FAILED'
        params_str = self._compact_json(entry.get('parameters', {}), max_length=220)
        summary_str = self._compact_json(entry.get('summary', {}), max_length=700)
        return (
            f"- Round {round_num} | Tool `{tool_name}` on {server} | {status} | "
            f"Params: {params_str} | Summary: {summary_str}"
        )

    def _compact_json(self, value: Any, max_length: int = 240) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        except Exception:
            text = str(value)
        return self._truncate_text(text, max_length)

    def _truncate_text(self, text: Any, max_length: Optional[int] = None) -> str:
        limit = max_length or self._planning_text_limit
        text = str(text)
        return text if len(text) <= limit else text[:limit] + "..."

    def _sanitize_structure(self, value: Any, depth: int = 0) -> Any:
        if depth >= 2:
            return self._truncate_text(self._compact_json(value, max_length=120), 120)

        if isinstance(value, dict):
            sanitized = {}
            for idx, (key, item) in enumerate(value.items()):
                if idx >= 8:
                    sanitized["..."] = f"{len(value) - 8} more keys omitted"
                    break
                sanitized[key] = self._sanitize_structure(item, depth + 1)
            return sanitized

        if isinstance(value, list):
            sanitized = [self._sanitize_structure(item, depth + 1) for item in value[:5]]
            if len(value) > 5:
                sanitized.append(f"... {len(value) - 5} more items omitted")
            return sanitized

        if isinstance(value, str):
            return self._truncate_text(value, 120)

        return value

    def _extract_reference_fields(self, item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        reference = {}
        id_keys = [
            'asin', 'fsq_id', 'id', 'business_id', 'place_id', 'venue_id',
            'product_id', 'item_id', 'uuid', 'slug'
        ]
        title_keys = ['title', 'name', 'display_name']

        for key in id_keys:
            value = item.get(key)
            if value not in (None, ''):
                reference[key] = self._truncate_text(value, 80)
                break

        for key in title_keys:
            value = item.get(key)
            if value not in (None, ''):
                reference[key] = self._truncate_text(value, 120)
                break

        return reference or None

    def _extract_top_item_refs(self, items: List[Any]) -> List[Dict[str, Any]]:
        refs = []
        for item in items[:20]:
            ref = self._extract_reference_fields(item)
            if ref:
                refs.append(ref)
            if len(refs) >= self._planning_item_ref_limit:
                break
        return refs

    def _extract_scalar_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        scalar_fields = {}
        skip_keys = {
            'items', 'results', 'data', 'entries', 'rows', 'records', 'businesses',
            'products', 'places', 'asins'
        }

        for key, value in data.items():
            if key in skip_keys or isinstance(value, (list, dict)):
                continue
            scalar_fields[key] = self._sanitize_structure(value)
            if len(scalar_fields) >= 6:
                break

        return scalar_fields

    def _extract_item_refs_summary(self, data: Any) -> Optional[Dict[str, Any]]:
        count_keys = ['total_results', 'total', 'count', 'num_results']

        if isinstance(data, dict):
            total_count = None
            for key in count_keys:
                value = data.get(key)
                if isinstance(value, (int, float)):
                    total_count = int(value)
                    break

            for key, value in data.items():
                if not isinstance(value, list):
                    continue
                refs = self._extract_top_item_refs(value)
                if not refs:
                    continue
                total = total_count if total_count is not None else len(value)
                metadata = self._extract_scalar_fields({k: v for k, v in data.items() if k != key})
                summary = {
                    'kind': 'items',
                    'list_key': key,
                    'total_results': total,
                    'top_item_refs': refs,
                    'omitted_items': max(total - len(refs), 0)
                }
                if metadata:
                    summary['metadata'] = metadata
                return summary

        if isinstance(data, list):
            refs = self._extract_top_item_refs(data)
            if refs:
                return {
                    'kind': 'items',
                    'list_key': 'list',
                    'total_results': len(data),
                    'top_item_refs': refs,
                    'omitted_items': max(len(data) - len(refs), 0)
                }

        return None

    def _summarize_result_for_planning(self, content: Any) -> Dict[str, Any]:
        if not isinstance(content, str):
            content = self._compact_json(content, max_length=2000)

        try:
            data = json.loads(content)
        except Exception:
            return {
                'kind': 'text',
                'preview': self._truncate_text(content, self._planning_text_limit)
            }

        item_summary = self._extract_item_refs_summary(data)
        if item_summary:
            return item_summary

        if isinstance(data, dict):
            scalar_fields = self._extract_scalar_fields(data)
            if scalar_fields:
                return {
                    'kind': 'json',
                    'fields': scalar_fields
                }
            return {
                'kind': 'json',
                'preview': self._compact_json(self._sanitize_structure(data), max_length=self._planning_text_limit)
            }

        if isinstance(data, list):
            return {
                'kind': 'list',
                'length': len(data),
                'sample': self._sanitize_structure(data[:3])
            }

        return {
            'kind': 'scalar',
            'value': self._truncate_text(data, self._planning_text_limit)
        }

    def _build_planning_state_entry(self, result: Dict[str, Any], round_num: int) -> Dict[str, Any]:
        entry = {
            'round': round_num,
            'tool': result.get('tool', 'unknown'),
            'server': result.get('server', 'unknown'),
            'parameters': self._sanitize_structure(result.get('parameters', {})),
            'success': result.get('success', False)
        }

        if result.get('success'):
            entry['summary'] = self._summarize_result_for_planning(result.get('result', ''))
        else:
            entry['summary'] = {
                'kind': 'error',
                'message': self._truncate_text(result.get('error', ''), config_loader.get_error_truncate_length())
            }

        return entry

    def _format_tools_for_prompt(self) -> str:
        """Format all available tools from all MCP servers for the planning prompt."""
        if not self.all_tools:
            return "No tools available."

        # Group tools by server
        servers = {}
        for tool_key, tool_info in self.all_tools.items():
            server = tool_info.get('server', 'Unknown')
            if server not in servers:
                servers[server] = []
            servers[server].append((tool_key, tool_info))

        lines = []
        tool_num = 1
        for server, tools in sorted(servers.items()):
            lines.append(f"[{server}]")
            for tool_key, tool_info in tools:
                description = tool_info.get('description', 'No description')
                if description and len(description) > 300:
                    description = description[:300] + "..."
                # Extract parameter names from input_schema
                schema = tool_info.get('input_schema', {})
                properties = schema.get('properties', {})
                required = schema.get('required', [])
                param_parts = []
                for param_name, param_schema in properties.items():
                    param_desc = param_schema.get('description', '')
                    is_required = param_name in required
                    req_label = '' if is_required else ' (optional)'
                    param_parts.append(f"{param_name}{req_label}: {param_desc}")
                params_str = '; '.join(param_parts) if param_parts else 'none'
                lines.append(f"  {tool_num}. {tool_key}")
                lines.append(f"     Description: {description}")
                lines.append(f"     Parameters: {params_str}")
                tool_num += 1
            lines.append("")
        return '\n'.join(lines)

    def _build_planning_prompt(self, task: str, round_num: int, execution_summary: str) -> str:
        """Build planning prompt based on execution mode.
        
        Single-round mode: simplified prompt for selecting a single tool.
        Multi-round mode: full prompt for strategic multi-tool parallel planning.
        """
        if self.single_round_mode:
            tools_section = self._format_tools_for_prompt()
            return f"""You are a tool selection expert. Choose the MOST APPROPRIATE tool to complete the task.

TASK: "{task}"

AVAILABLE TOOLS:
{tools_section}
{execution_summary}

Select the SINGLE most appropriate tool for this task and return JSON:
{{
    "reasoning": "<Why this tool is the best choice>",
    "should_continue": true,
    "planned_tools": [
        {{
            "tool": "<server_name>:<tool_name>",
            "parameters": {{ ... }}
        }}
    ]
}}

Return ONLY the JSON object.
"""
        elif self.serial_mode:
            # Build candidate bus section for serial mode
            bus_section = self._render_candidate_bus()
            if bus_section:
                bus_section = f"\n{bus_section}\n"
            else:
                bus_section = "\nCANDIDATE BUS: empty (first round, no previous results yet)\n"

return f"""You are a strategic decision-making expert for a multi-tool AI agent. The task requires STRICTLY SEQUENTIAL tool execution ?each tool's output feeds into the next tool's input.

TASK: "{task}"
CURRENT ROUND: {round_num}
AVAILABLE TOOLS ACROSS SERVERS:
{MCPConnector.format_tools_for_prompt(self.all_tools)}
{execution_summary}
{bus_section}
STRICT SERIAL EXECUTION RULES:
1. Plan EXACTLY ONE tool call per round ?NEVER more than one
2. Each tool call should use information obtained from PREVIOUS rounds' results
3. Analyze the output from the previous round before deciding the next tool
4. Follow the task's dependency chain: each step depends on the prior step's output
5. Do NOT call tools whose required input data is not yet available
6. You have {config_loader.get_max_execution_rounds()} rounds in total for solving the task
7. CRITICAL: Use EXACT concrete values from the CANDIDATE BUS above when filling tool parameters.
For example, if the bus shows items_ids=["B00OLNX4BE", ...], use "B00OLNX4BE" directly ? NEVER use placeholder strings like "<most_recent_item_id>" or "<ASIN_from_round_1>".
8. CANDIDATE WHITELIST FILTERING: When the task mentions a specific set of candidate ASINs/business_ids/item_ids
   and you are calling a FILTER or SEARCH tool (e.g., filter_products, filter_items_by_attributes,
   search_keyword, search_reviews, query_sentiment), you MUST pass those candidate IDs via the tool's
   `asins` / `business_ids` / `item_ids` parameter so the filter is restricted to the candidate set.
   Without this whitelist parameter, the tool returns full-database results that are NOT limited to the
   user's candidate pool, which typically breaks downstream reasoning. ALWAYS prefer passing the
   whitelist when the task refers to "from the following ASINs", "among these candidates", etc.
9. DO NOT REPEAT a tool call with the exact same parameters that has already succeeded in a previous round.

DECISION AND PLANNING:
1. Assess if the original task is fully completed based on accumulated results
2. If not complete, identify the NEXT SINGLE tool in the dependency chain
3. Extract required parameters from the CANDIDATE BUS ?use the exact values listed there
4. Plan exactly ONE tool call for this round

Return your response in this exact JSON format:
{{
    "reasoning": "<Explain which previous result you are using and why this specific tool is the next step in the chain>",
    "should_continue": <true/false>,
    "planned_tools": [
        {{
            "tool": "server:tool_name",
            "parameters": {{ "param": "value" }}
        }}
    ]
}}

CRITICAL: planned_tools MUST contain AT MOST 1 tool. Serial execution means ONE tool per round.
If the task is complete, set "should_continue" to false and "planned_tools" to [].
Return ONLY the JSON object.
"""
        else:
            return f"""You are a strategic decision-making expert for a multi-tool AI agent using the provided tools to perform the task.

TASK: "{task}"
CURRENT ROUND: {round_num}
AVAILABLE TOOLS ACROSS SERVERS:
{MCPConnector.format_tools_for_prompt(self.all_tools)}
{execution_summary}

DECISION AND PLANNING:
1. Assess if the original task is fully completed
2. If not complete, decide if another round would provide significant value
3. If continuing, plan PARALLEL tool executions for this round

PARALLEL EXECUTION PLANNING (if continuing):
- Plan ALL tool calls for this round to execute in PARALLEL
- ALL tools in this round will run simultaneously without dependencies
- EARLY EXECUTION PRINCIPLE: Plan all necessary tool calls that don't require dependencies from other tools in this round
- AVOID REDUNDANT CALLS: Don't repeat successful tools unless specifically needed
- BUILD ON PREVIOUS RESULTS: Use information from previous rounds
- FOCUS ON INDEPENDENT TASKS: Plan tools that can work with currently available information
- You only have {config_loader.get_max_execution_rounds()} rounds in total for solving the task.

Return your response in this exact JSON format:
{{
    "reasoning": "<Detailed explanation for your decision and parallel execution plan>",
    "should_continue": <true/false>,
    "planned_tools": [
        {{
            "tool": "server:tool_name",
            "parameters": {{ "param": "value" }}
        }}
    ]
}}

EXAMPLES:
{self.examples}

PARALLEL EXECUTION RULES:
- ALL tools in this round will run simultaneously
- NO dependencies between tools within the same round
- Each tool should work independently with available information

If not continuing, set "planned_tools" to an empty array [].
If continuing but no executions needed, also set "planned_tools" to an empty array [].
Return ONLY the JSON object.
"""

    async def _fix_invalid_json_format(self, response_str: str, result: Any, round_num: int) -> dict:
        """Fix invalid JSON format from LLM response."""
        logger.warning(f"Attempting to fix invalid format for round {round_num}: {type(result)}")
        
        # Build correction prompt
        fix_prompt = f"""
        The previous response was not in the correct JSON format.
        Original response: {response_str}
        
        Please convert it to this exact format:
        {{
            "reasoning": "<explanation of decision and plan>",
            "should_continue": <true/false>,
            "planned_tools": [
                {{
                    "tool": "server:tool_name",
                    "parameters": {{}}
                }}
            ]
        }}
        
        If the original response was a list of tools, put them in "planned_tools".
        Return ONLY the corrected JSON object.
        """
        
        try:
            # Use LLM to fix the format
            fixed_response = await self.llm.get_completion(
                "You are a JSON format corrector. Convert the input to the specified JSON structure.",
                fix_prompt,
                config_loader.get_format_conversion_tokens()  # Small token limit for format conversion
            )
            fixed_result = self.llm.clean_and_parse_json(fixed_response)
            logger.warning(f"Original response: {response_str}")
            logger.warning(f"Fixed response: {fixed_response}")
            logger.warning(f"Fixed result: {fixed_result}")
            
            # Validate the fixed result
            if isinstance(fixed_result, dict) and "should_continue" in fixed_result:
                logger.info(f"Successfully fixed JSON format for round {round_num}")
                return fixed_result
        except Exception as fix_error:
            logger.error(f"Failed to fix JSON format via LLM: {fix_error}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Fallback: provide default structure based on the invalid result
        if isinstance(result, list):
            return {
                "reasoning": "LLM returned list format, assumed as planned_tools",
                "should_continue": len(result) > 0 and round_num < config_loader.get_max_execution_rounds(),
                "planned_tools": result
            }
        else:
            return {
                "reasoning": "Failed to parse LLM response",
                "should_continue": False,
                "planned_tools": []
            }

    async def _plan_next_actions(self, task: str, round_num: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Multi-layered retry strategy for planning with ExecutionContext management."""
        logger.info(f"Planning next actions for round {round_num}")
        
        # Create new execution context for each planning call
        ctx = ExecutionContext()
        original_max_tokens = config_loader.get_planning_tokens()
        
        # Multi-layered retry strategy
        while ctx.can_retry_task():
            # Only show retry message if this is actually a retry (not the first attempt)
            if ctx.current_task_retry > 1:
                logger.info(f"Task retry {ctx.current_task_retry}/{ctx.max_task_retries} - {ctx.get_status_summary()}")
            
            while ctx.can_retry_round():
                # Only show round message if this is actually a retry (not the first round)
                if ctx.current_round > 1:
                    logger.info(f"Round retry {ctx.current_round}/{ctx.max_rounds} - {ctx.get_status_summary()}")
                
                # Build initial prompt
                execution_summary = self._build_execution_summary()
                prompt = self._build_planning_prompt(task, round_num, execution_summary)
                if self.single_round_mode:
                    system_prompt = (
                        f"You are a tool selection expert for Round {round_num}. "
                        f"Plan EXACTLY ONE tool execution for this round. Do not plan multiple tools."
                    )
                elif self.serial_mode:
                    system_prompt = (
                        f"You are a strategic multi-tool AI agent planner for Round {round_num}. "
f"You MUST plan EXACTLY ONE tool call per round. Tools MUST be executed STRICTLY SEQUENTIALLY ?"
                        f"each tool's output is needed as input for the next tool. "
                        f"NEVER plan more than one tool in a single round. "
                        f"After each round, analyze the returned result and decide which tool to call next based on the output. "
                        f"CRITICAL: Always use the EXACT concrete values from the CANDIDATE BUS for tool parameters. "
                        f"NEVER use placeholder strings like '<item_id>' or '<ASIN_from_round_1>'. "
                        f"Do NOT repeat tools that have already returned successful results with the same parameters."
                    )
                else:
                    system_prompt = (
                        f"You are a strategic multi-tool AI agent planner for Round {round_num}. "
                        f"Plan ALL independent tool executions for this round so they can run in PARALLEL. "
                        f"Group as many non-dependent tools as possible into a single round to maximize efficiency. "
                        f"Do NOT repeat tools that have already returned successful results with the same parameters."
                    )
                
                # Save prompt to history
                self.prompts_history.append({
                    "type": "planning",
                    "round": round_num,
                    "system_prompt": system_prompt,
                    "user_prompt": prompt
                })
                
                # Log the complete prompt for debugging
                logger.info(f"\n{'='*80}\n[PROMPT DEBUG] Round {round_num} - System Prompt:\n{system_prompt}\n{'='*80}")
                logger.info(f"\n{'='*80}\n[PROMPT DEBUG] Round {round_num} - User Prompt:\n{prompt}\n{'='*80}")
                
                # Retry with token reduction and format fixes
                result = None  # Initialize result
                while True:
                    try:
                        # Apply token reduction if needed
                        current_max_tokens = original_max_tokens
                        if ctx.current_token_reduction > 0:
                            current_max_tokens = ctx.apply_token_reduction(original_max_tokens)
                        
                        # Make LLM call with token tracking
                        response_data = await self.llm.get_completion(
                            system_prompt, 
                            prompt, 
                            current_max_tokens,
                            return_usage=True
                        )
                        
                        # Handle both tuple and string returns
                        if isinstance(response_data, tuple):
                            response_str, usage = response_data
                            if usage:
                                self.total_output_tokens += usage.get('completion_tokens', 0)
                                self.total_prompt_tokens += usage.get('prompt_tokens', 0)
                                self.total_tokens += usage.get('total_tokens', 0)
                        else:
                            response_str = response_data
                        
                        # Save response to history
                        if self.prompts_history and self.prompts_history[-1]["round"] == round_num:
                            self.prompts_history[-1]["llm_response"] = response_str
                        
                        # Log the LLM response
                        logger.debug(f"\n{'='*80}\n[RESPONSE DEBUG] Round {round_num} - LLM Response:\n{response_str}\n{'='*80}")
                        
                        # Check for empty response
                        if not response_str or response_str.strip() == "":
                            if ctx.can_compress():
                                logger.info("Empty response detected, triggering planning-state compression...")
                                if await self.compress_planning_state():
                                    ctx.mark_compressed()
                                    ctx.current_token_reduction = 0  # Reset token reduction
                                    execution_summary = self._build_execution_summary()
                                    prompt = self._build_planning_prompt(task, round_num, execution_summary)
                                    continue
                            raise ValueError("Empty response received from LLM")
                        
                        # Parse JSON
                        try:
                            result = self.llm.clean_and_parse_json(response_str)
                        except Exception as parse_error:
                            logger.warning(f"JSON parse error: {parse_error}")
                            result = None
                        
                        # Check format and fix if needed
                        if not isinstance(result, dict) or "should_continue" not in result:
                            if ctx.can_fix_format():
                                ctx.increment_format_fixes()
                                logger.info(f"Invalid format detected, attempting fix {ctx.current_format_fixes}/{ctx.max_format_fixes}")
                                result = await self._fix_invalid_json_format(response_str, result, round_num)
                                
                                if isinstance(result, dict) and "should_continue" in result:
                                    logger.info("Format fix successful")
                                    break  # Success
                                else:
                                    continue  # Try format fix again
                            else:
                                logger.warning("Format fix attempts exhausted")
                                result = None
                                break  # Exit inner loop
                        else:
                            logger.info("Planning successful")
                            break  # Success
                    
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(f"ERROR in planning attempt: {e}")
                        import traceback
                        logger.error(f"Full traceback: {traceback.format_exc()}")
                        
                        # Check for token limit errors
                        if self._is_token_limit_error(error_msg):
                            if ctx.can_reduce_tokens():
                                ctx.current_token_reduction += 1
                                logger.info(f"Token limit error, applying reduction {ctx.current_token_reduction}/{ctx.max_token_reductions}")
                                continue  # Retry with reduced tokens
                            elif ctx.can_compress():
                                logger.info("Token reduction exhausted, triggering planning-state compression...")
                                if await self.compress_planning_state():
                                    ctx.mark_compressed()
                                    ctx.current_token_reduction = 0
                                    execution_summary = self._build_execution_summary()
                                    prompt = self._build_planning_prompt(task, round_num, execution_summary)
                                    continue
                        
                        # For other errors, check if compression is available
                        elif ctx.can_compress():
                            logger.info(f"Planning error, triggering planning-state compression: {e}")
                            if await self.compress_planning_state():
                                ctx.mark_compressed()
                                ctx.current_token_reduction = 0
                                execution_summary = self._build_execution_summary()
                                prompt = self._build_planning_prompt(task, round_num, execution_summary)
                                continue
                        
                        # No more retries possible
                        result = None
                        break
                
                # Check if we got a valid result
                if isinstance(result, dict) and "should_continue" in result:
                    # Success! Return the result
                    should_continue = result.get("should_continue", round_num <= 1)
                    reasoning = result.get("reasoning", "No reasoning provided.")
                    planned_tools = result.get("planned_tools", [])
                    
                    executions = []
                    if isinstance(planned_tools, list):
                        for tool_plan in planned_tools:
                            if isinstance(tool_plan, dict):
                                self._total_planned_tools += 1
                                if tool_plan.get('tool'):
                                    self._valid_planned_tools += 1
                                    executions.append(tool_plan)
                    
                    logger.info(f"Planning successful - Continue={should_continue}, Planned {len(executions)} executions")
                    return should_continue, reasoning, executions
                
                # Round failed, try next round
                if ctx.can_retry_round():
                    logger.info(f"Round failed, waiting {config_loader.get_retry_delay()} seconds before next round...")
                    await asyncio.sleep(config_loader.get_retry_delay())  
                    ctx.start_new_round()
                else:
                    break  # No more rounds
            
            # All rounds failed, try new task retry
            if ctx.can_retry_task():
                logger.info("All rounds failed, starting new task retry...")
                ctx.start_new_task_retry()
            else:
                break  # No more task retries
        
        # All retries exhausted
        logger.error(f"All retry attempts exhausted for round {round_num}")
        return False, "All planning attempts failed", []


    async def _execute_planned_tools(self, executions: List[Dict[str, Any]], round_num: int) -> List[Dict[str, Any]]:
        """Executes a list of planned tool calls, handling sequential-only tools separately."""
        logger.info(f"Executing {len(executions)} planned tools for round {round_num}.")
        
        # Get sequential-only tools from config
        sequential_only_tools = config_loader.get_sequential_only_tools()
        
        # Separate sequential and concurrent executions
        sequential_executions = []
        concurrent_executions = []
        
        for exec in executions:
            tool_name = exec.get("tool")
            if tool_name in sequential_only_tools:
                sequential_executions.append(exec)
            else:
                concurrent_executions.append(exec)
        
        logger.info(f"Sequential tools: {len(sequential_executions)}, Concurrent tools: {len(concurrent_executions)}")
        
        # Group concurrent executions by server
        server_executions = {}
        for exec in concurrent_executions:
            tool_name = exec.get("tool")
            if tool_name and tool_name in self.all_tools:
                server_name = self.all_tools[tool_name]["server"]
            else:
                server_name = "unknown"
            
            if server_name not in server_executions:
                server_executions[server_name] = []
            server_executions[server_name].append(exec)
        
        server_semaphores = {server: asyncio.Semaphore(config_loader.get_server_semaphore_limit()) for server in server_executions}
        
        async def execute_one(execution: Dict[str, Any], semaphore: asyncio.Semaphore) -> Dict[str, Any]:
            async with semaphore:
                tool_name = execution.get("tool")
                params = execution.get("parameters", {})
                
                if not tool_name or tool_name not in self.all_tools:
                    error_msg = f"Tool '{tool_name}' not found or not specified."
                    logger.error(f"  - {error_msg}")
                    
                    # Record failed tool call to history
                    self.tool_calls_history.append({
                        "round": round_num,
                        "tool": tool_name,
                        "server": "unknown",
                        "parameters": params,
                        "success": False,
                        "error": error_msg
                    })
                    
                    return {"tool": tool_name, "parameters": params, "round_num": round_num, "error": error_msg, "success": False}

                try:
                    result_obj = await self.server_manager.call_tool(tool_name, params)
                    
                    is_error = hasattr(result_obj, 'isError') and result_obj.isError
                    result_text = self._extract_text_from_result(result_obj)

                    server_name = self.all_tools[tool_name]["server"]

                    if is_error:
                        logger.warning(f"  - Tool `{tool_name}` on {server_name} failed with error: {result_text[:config_loader.get_error_display_prefix()]}...")
                        
                        # Record failed tool call to history
                        self.tool_calls_history.append({
                            "round": round_num,
                            "tool": tool_name,
                            "server": server_name,
                            "parameters": params,
                            "success": False,
                            "error": result_text[:500]  # Truncate error message
                        })
                        
                        return {"tool": tool_name, "server": server_name, "parameters": params, "round_num": round_num, "error": result_text, "success": False}
                    else:
                        logger.info(f"  - Tool `{tool_name}` on {server_name} call successful.")
                        
                        # In multi-round mode (L2/L3), slim down results:
                        # keep only item IDs (asin/id/fsq_id/...) and limit to top 10
                        if not self.single_round_mode:
                            simplified_result = self._slim_tool_result(result_text, top_k=10)
                        else:
                            simplified_result = str(result_text)

                        result_preview = simplified_result[:200] + "..." if len(simplified_result) > 200 else simplified_result
                        logger.info(f"    Tool result: {result_preview}")
                        
                        # Record tool call to history
                        self.tool_calls_history.append({
                            "round": round_num,
                            "tool": tool_name,
                            "server": server_name,
                            "parameters": params,
                            "success": True
                        })
                        
                        return {"tool": tool_name, "server": server_name, "parameters": params, "round_num": round_num, "result": simplified_result, "result_raw": result_text, "success": True}

                except Exception as e:
                    logger.error(f"ERROR in tool call '{tool_name}': {e}")
                    import traceback
                    logger.error(f"Full traceback: {traceback.format_exc()}")
                    server_name = self.all_tools.get(tool_name, {}).get("server", "unknown")
                    
                    # Record exception tool call to history
                    self.tool_calls_history.append({
                        "round": round_num,
                        "tool": tool_name,
                        "server": server_name,
                        "parameters": params,
                        "success": False,
                        "error": str(e)[:500]  # Truncate error message
                    })
                    
                    return {"tool": tool_name, "server": server_name, "parameters": params, "round_num": round_num, "error": str(e), "success": False}
        
        # Execute sequential tools first (one by one)
        sequential_results = []
        if sequential_executions:
            logger.info(f"Executing {len(sequential_executions)} sequential tools...")
            dummy_semaphore = asyncio.Semaphore(1)  # Limit to 1 to ensure sequential execution
            for exec in sequential_executions:
                logger.info(f"  Executing sequential tool: {exec.get('tool')}")
                result = await execute_one(exec, dummy_semaphore)
                sequential_results.append(result)
                logger.info(f"  Sequential tool {exec.get('tool')} completed: {'SUCCESS' if result.get('success') else 'FAILED'}")
        
        # Execute concurrent tools (existing logic)
        concurrent_results = []
        if concurrent_executions:
            logger.info(f"Executing {len(concurrent_executions)} concurrent tools...")
            execution_requests = []
            for server, server_execs in server_executions.items():
                semaphore = server_semaphores.get(server, asyncio.Semaphore(config_loader.get_server_semaphore_limit()))
                for exec in server_execs:
                    execution_requests.append(execute_one(exec, semaphore))
            
            concurrent_results = await asyncio.gather(*execution_requests)
        
        # Combine results maintaining execution order
        results = sequential_results + concurrent_results
        
        # Validate that all results are dictionaries with required fields
        for i, result in enumerate(results):
            if not isinstance(result, dict):
                raise RuntimeError(f"Tool execution {i} returned {type(result)} instead of dict - this is a bug")
            if 'success' not in result:
                raise RuntimeError(f"Tool execution {i} missing 'success' field - this is a bug")
            if 'tool' not in result:
                raise RuntimeError(f"Tool execution {i} missing 'tool' field - this is a bug")
        
        return results

    async def _update_state(self, round_results: List[Dict[str, Any]], round_num: int) -> None:
        """Update the accumulated information and execution results after a round.
        
        Args:
            round_results: List of execution results from the current round
            round_num: Current round number
            
        Raises:
            RuntimeError: If round results have invalid format
        """
        # Validate round_results before adding to execution_results
        for i, result in enumerate(round_results):
            if not isinstance(result, dict):
                raise RuntimeError(f"Round {round_num} result {i} is {type(result)} instead of dict - this is a bug")
            if 'success' not in result or 'tool' not in result:
                raise RuntimeError(f"Round {round_num} result {i} missing required fields - this is a bug")
        
        self.execution_results.extend(round_results)
        
        round_summary = f"\n\n--- Summary of Round {round_num} ---\n"
        
        if self.concurrent_summarization:
            # Concurrent summarization mode
            logger.info(f"Using concurrent summarization for {len(round_results)} results")
            
            async def process_result_concurrent(result):
                server = result.get('server', 'unknown')
                tool_name = result['tool']
                parameters = result.get('parameters', {})
                
                # Format parameters for display
                params_str = f"{parameters}" if parameters else "{}"
                
                if result['success']:
                    content = result['result']
                    # Result is already simplified to asin-only format
                    
                    token_count = self._estimate_token_count(content)
                    
                    if token_count <= config_loader.get_content_summary_threshold():
                        return f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result: {content}\n"
                    else:
                        logger.info(f"Summarizing large result from {tool_name} ({token_count} tokens)")
                        try:
                            summarized_content = await self._summarize_content(content, "result")
                            return f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result (summarized from {token_count} tokens): {summarized_content[:config_loader.get_content_truncate_length()]}\n"
                        except Exception as e:
                            logger.error(f"ERROR in summarizing result from {tool_name}: {e}")
                            import traceback
                            logger.error(f"Full traceback: {traceback.format_exc()}")
                            return f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result (truncated): {content[:config_loader.get_content_truncate_length()]}...\n"
                else:
                    error_content = result['error']
                    token_count = self._estimate_token_count(error_content)
                    
                    if token_count <= config_loader.get_content_summary_threshold():
                        return f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error: {error_content}\n"
                    else:
                        logger.info(f"Summarizing large error from {tool_name} ({token_count} tokens)")
                        try:
                            summarized_error = await self._summarize_content(error_content, "error")
                            return f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error (summarized from {token_count} tokens): {summarized_error[:config_loader.get_error_truncate_length()]}\n"
                        except Exception as e:
                            logger.error(f"ERROR in summarizing error from {tool_name}: {e}")
                            import traceback
                            logger.error(f"Full traceback: {traceback.format_exc()}")
                            return f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error (truncated): {error_content[:config_loader.get_error_truncate_length()]}...\n"
            
            # Process all results concurrently
            result_summaries = await asyncio.gather(
                *[process_result_concurrent(result) for result in round_results],
                return_exceptions=True
            )
            
            # Add all summaries to round_summary
            for summary in result_summaries:
                if isinstance(summary, str):
                    round_summary += summary
                else:
                    logger.error(f"Error in concurrent summarization: {summary}")
                    round_summary += "Error processing result\n"
        else:
            # Sequential summarization mode (original)
            for result in round_results:
                server = result.get('server', 'unknown')
                tool_name = result['tool']
                parameters = result.get('parameters', {})
                
                # Format parameters for display
                params_str = f"{parameters}" if parameters else "{}"
                
                if result['success']:
                    content = result['result']
                    # Result is already simplified to asin-only format
                    
                    token_count = self._estimate_token_count(content)
                    
                    if token_count <= config_loader.get_content_summary_threshold():
                        round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result: {content}\n"
                    else:
                        logger.info(f"Summarizing large result from {tool_name} ({token_count} tokens)")
                        try:
                            summarized_content = await self._summarize_content(content, "result")
                            round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result (summarized from {token_count} tokens): {summarized_content[:config_loader.get_content_truncate_length()]}\n"
                        except Exception as e:
                            logger.error(f"ERROR in summarizing result from {tool_name}: {e}")
                            import traceback
                            logger.error(f"Full traceback: {traceback.format_exc()}")
                            round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} succeeded. Result (truncated): {content[:config_loader.get_content_truncate_length()]}...\n"
                else:
                    error_content = result['error']
                    token_count = self._estimate_token_count(error_content)
                    
                    if token_count <= config_loader.get_content_summary_threshold():
                        round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error: {error_content}\n"
                    else:
                        logger.info(f"Summarizing large error from {tool_name} ({token_count} tokens)")
                        try:
                            summarized_error = await self._summarize_content(error_content, "error")
                            round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error (summarized from {token_count} tokens): {summarized_error[:config_loader.get_error_truncate_length()]}\n"
                        except Exception as e:
                            logger.error(f"ERROR in summarizing error from {tool_name}: {e}")
                            import traceback
                            logger.error(f"Full traceback: {traceback.format_exc()}")
                            round_summary += f"Tool `{tool_name}` with Parameter {params_str} on {server} failed. Error (truncated): {error_content[:config_loader.get_error_truncate_length()]}...\n"
        
        self.accumulated_information += round_summary
        # Also update uncompressed version
        self.accumulated_information_uncompressed += round_summary
        self.planning_state.extend(
            self._build_planning_state_entry(result, round_num) for result in round_results
        )
        # Update candidate bus with concrete entity IDs from this round
        # Use result_raw (unsimplified) when available so bus captures full metadata
        for result in round_results:
            self._extract_bus_entries_from_result(result, round_num)
        logger.info(f"Round {round_num} finished. Total executions so far: {len(self.execution_results)}. Candidate bus entries: {len(self.candidate_bus)}.")

    def _extract_asin_title_only(self, content: str) -> str:
        """Extract only asin from JSON content containing items list.
        
        Args:
            content: JSON string containing tool result with items
            
        Returns:
            Simplified JSON string with only asin per item
        """
        try:
            import json
            data = json.loads(content)
            
            # Check if result contains items list
            if isinstance(data, dict) and 'items' in data and isinstance(data['items'], list):
                # Only extract asin list
                asin_list = []
                for item in data['items']:
                    if isinstance(item, dict) and 'asin' in item:
                        asin_list.append(item['asin'])
                
                # Reconstruct result with only asin list
                simplified_data = {
                    'total_results': data.get('total_results', len(asin_list)),
                    'asins': asin_list
                }
                
                return json.dumps(simplified_data, ensure_ascii=False)
            
            # If not items list format, return original content
            return content
            
        except Exception as e:
            logger.warning(f"Failed to extract asin: {e}, returning original content")
            return content

    def _slim_tool_result(self, content: str, top_k: int = 10) -> str:
        """Slim down tool result for multi-round execution.
        
        For results containing item lists, only keep item IDs (asin/id/fsq_id/business_id)
        and limit to top_k items. Preserves scalar fields and non-list results as-is.
        
        Args:
            content: JSON string of tool result
            top_k: Maximum number of item IDs to retain (default 10)
            
        Returns:
            Slimmed JSON string
        """
        try:
            data = json.loads(content)
        except Exception:
            return content

        if isinstance(data, list):
            return self._slim_item_list(data, 'list', top_k)

        if not isinstance(data, dict):
            return content

        # ID field priority per dataset
        id_keys = ['asin', 'fsq_id', 'business_id', 'id', 'place_id', 'venue_id', 'product_id', 'item_id']
        list_keys = ['items', 'results', 'businesses', 'places', 'products', 'data', 'entries', 'rows', 'records']

        for lk in list_keys:
            items = data.get(lk)
            if not isinstance(items, list) or not items:
                continue
            if not isinstance(items[0], dict):
                continue

            # Find which ID key exists in the first item
            chosen_id_key = None
            for ik in id_keys:
                if ik in items[0]:
                    chosen_id_key = ik
                    break

            if chosen_id_key is None:
                continue

            total = len(items)
            id_list = []
            for item in items[:top_k]:
                val = item.get(chosen_id_key)
                if val is not None:
                    id_list.append(val)

            # Preserve scalar fields from the original dict
            slim = {}
            for k, v in data.items():
                if k == lk:
                    continue
                if not isinstance(v, (list, dict)):
                    slim[k] = v

            slim['total_results'] = data.get('total_results', total)
            slim[f'{chosen_id_key}s'] = id_list
            if total > top_k:
                slim['omitted'] = total - top_k

            return json.dumps(slim, ensure_ascii=False)

        # No item list found, return original
        return content

    def _slim_item_list(self, items: list, list_key: str, top_k: int) -> str:
        """Slim a top-level list of items."""
        id_keys = ['asin', 'fsq_id', 'business_id', 'id', 'place_id', 'venue_id', 'product_id', 'item_id']
        if items and isinstance(items[0], dict):
            chosen_id_key = None
            for ik in id_keys:
                if ik in items[0]:
                    chosen_id_key = ik
                    break
            if chosen_id_key:
                total = len(items)
                id_list = [item.get(chosen_id_key) for item in items[:top_k] if item.get(chosen_id_key) is not None]
                slim = {'total_results': total, f'{chosen_id_key}s': id_list}
                if total > top_k:
                    slim['omitted'] = total - top_k
                return json.dumps(slim, ensure_ascii=False)
        # Fallback: truncate list
        return json.dumps(items[:top_k], ensure_ascii=False)

    def _extract_items_count(self, content: str) -> int:
        """Extract item count from JSON content."""
        try:
            import json
            data = json.loads(content)
            
            if isinstance(data, list):
                return len(data)
            
            if isinstance(data, dict):
                list_keys = [
                    'items', 'asins', 'results', 'data', 'models', 'datasets',
                    'spaces', 'papers', 'collections', 'entries', 'rows'
                ]
                for key in list_keys:
                    value = data.get(key)
                    if isinstance(value, list):
                        return len(value)
                
                count_keys = ['total_results', 'total', 'count', 'num_results']
                for key in count_keys:
                    if key in data:
                        return int(data[key])
        except Exception:
            pass
        
        try:
            return int(content)
        except Exception:
            return 0


    async def _synthesize_final_solution(self, task: str, total_executions: int) -> str:
        """LLM synthesizes a final, comprehensive solution from all execution results."""
        logger.info("Synthesizing final solution from all rounds...")

        prompt = f"""You are an expert solution synthesizer for multi-tool AI agent execution.
        ORIGINAL TASK: "{task}"
        A multi-round execution process has completed with {total_executions} total tool calls across multiple MCP servers.
        ACCUMULATED INFORMATION AND RESULTS:
        {self.accumulated_information}
        Based on the original task and all the information gathered from multiple servers, provide a final answer. Do NOT include any other fields or commentary.
        Format the response as a concise list of items.
        """
        system_prompt = "You are an expert solution synthesizer specializing in multi-server AI agent results. Combine information from different servers into a cohesive, high-quality answer."

        # Save synthesis prompt to history
        self.prompts_history.append({
            "type": "synthesis",
            "system_prompt": system_prompt,
            "user_prompt": prompt
        })

        # Log synthesis prompts
        logger.info(f"\n{'='*80}\n[SYNTHESIS DEBUG] System Prompt:\n{system_prompt}\n{'='*80}")
        logger.info(f"\n{'='*80}\n[SYNTHESIS DEBUG] User Prompt:\n{prompt}\n{'='*80}")

        # Simple retry with potential compression
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response_data = await self.llm.get_completion(
                    system_prompt, 
                    prompt, 
                    config_loader.get_planning_tokens(),
                    return_usage=True
                )
                
                # Handle both tuple and string returns
                if isinstance(response_data, tuple):
                    solution, usage = response_data
                    if usage:
                        self.total_output_tokens += usage.get('completion_tokens', 0)
                        self.total_prompt_tokens += usage.get('prompt_tokens', 0)
                        self.total_tokens += usage.get('total_tokens', 0)
                else:
                    solution = response_data
                
                # Save synthesis response to history
                if self.prompts_history and self.prompts_history[-1]["type"] == "synthesis":
                    self.prompts_history[-1]["llm_response"] = solution
                
                # Log synthesis response
                logger.debug(f"\n{'='*80}\n[SYNTHESIS DEBUG] Final Solution:\n{solution}\n{'='*80}")
                
                return solution
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"ERROR in final solution attempt {attempt + 1}/{max_retries}: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                
                # Try compression on token limit errors
                if self._is_token_limit_error(error_msg) and attempt < max_retries - 1:
                    logger.info("Token limit error in final solution, attempting compression...")
                    if await self.compress_accumulated_information():
                        # Regenerate prompt with compressed context
                        prompt = f"""You are an expert solution synthesizer for multi-tool AI agent execution.
                        ORIGINAL TASK: "{task}"
                        A multi-round execution process has completed with {total_executions} total tool calls across multiple MCP servers.
                        ACCUMULATED INFORMATION AND RESULTS:
                        {self.accumulated_information}
                        Based on the original task and all the information gathered from multiple servers, provide a final answer. Do NOT include any other fields or commentary.
                        Format the response as a concise list of items.
                        """
                        continue
                
                # If this is the last attempt, re-raise the error
                if attempt == max_retries - 1:
                    raise e
        
        # Should not reach here
        return "Error: Failed to synthesize final solution"
        
    @staticmethod
    @handle_errors("extracting text from result", reraise=False)
    def _extract_text_from_result(result) -> str:
        """Extracts plain text from a CallToolResult object."""
        if hasattr(result, 'content') and result.content:
            texts = []
            for item in result.content:
                if isinstance(item, dict):
                    text = item.get('text')
                    if text:
                        texts.append(text)
                        continue
                if hasattr(item, 'text'):
                    text = getattr(item, 'text')
                    if text:
                        texts.append(text)
            if texts:
                return "".join(texts)
        if isinstance(result, dict):
            text = result.get('text')
            if isinstance(text, str) and text:
                return text
        result_str = str(result)
        try:
            import re
            match = re.search(r"text='(.*?)'", result_str, re.DOTALL)
            if match:
                extracted = match.group(1)
                try:
                    extracted = bytes(extracted, "utf-8").decode("unicode_escape")
                except Exception:
                    pass
                return extracted
        except Exception:
            pass
        return result_str
    
    @handle_errors("estimating token count", reraise=False)
    def _estimate_token_count(self, text: str) -> int:
        """Estimate token count using character-based approximation."""
# Rough approximation: 1 token ?4 characters for most languages
        return len(text) // 4
    
    @handle_errors("checking content filter error", reraise=False)
    def _is_content_filter_error(self, error_message: str) -> bool:
        """Check if the error is related to Azure content filtering."""
        error_lower = str(error_message).lower()
        content_filter_indicators = [
            "content management policy",
            "content filtering policies",
            "content_filter",
            "jailbreak",
            "responsibleaipolicyviolation"
        ]
        return any(indicator in error_lower for indicator in content_filter_indicators)
    
    @handle_errors("checking token limit error", reraise=False)
    def _is_token_limit_error(self, error_message: str) -> bool:
        """Check if the error is related to token limits."""
        error_lower = str(error_message).lower()
        token_limit_indicators = [
            "maximum context length",
            "context length",
            "token limit",
            "too many tokens",
            "exceeds maximum",
            "requested too many tokens"
        ]
        return any(indicator in error_lower for indicator in token_limit_indicators)

    @handle_errors("creating fallback LLM", reraise=False)
    async def _get_fallback_llm(self):
        """Get fallback LLM for content filtering issues."""
        from llm.factory import LLMFactory
        model_configs = LLMFactory.get_model_configs()
        
        # Try to get fallback model
        fallback_config = model_configs.get('fallback-model')
        if not fallback_config:
            logger.warning("Fallback model not available")
            return None
            
        fallback_llm = await LLMFactory.create_llm_provider(fallback_config)
        logger.info("Created fallback LLM for content summarization")
        return fallback_llm

    async def _summarize_content(self, content: str, content_type: str = "result") -> str:
        """Summarize content using LLM to keep it under threshold tokens."""
        system_prompt = f"You are a helpful assistant. I need your help to extract key information from content."
        
        user_prompt = f"""Summarize the following content to less than {config_loader.get_content_summary_threshold()} tokens while preserving all important information: CONTENT: {content} SUMMARIZED CONTENT:"""
        
        try:
            summary = await self.llm.get_completion(
                system_prompt, 
                user_prompt[:config_loader.get_user_prompt_max_length()], 
                config_loader.get_summarization_max_tokens()
            )
            return summary.strip()
            
        except Exception as e:
            logger.error(f"ERROR in primary model summarizing {content_type} content: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Check if this is a content filter error
            if self._is_content_filter_error(str(e)):
                logger.info("Content filter error detected, attempting fallback model")
                
                try:
                    fallback_llm = await self._get_fallback_llm()
                    if fallback_llm:
                        logger.info("Using fallback model for content summarization")
                        summary = await fallback_llm.get_completion(
                            system_prompt, 
                            user_prompt[:config_loader.get_user_prompt_max_length()], 
                            3000
                        )
                        logger.info("Successfully summarized using fallback model")
                        return summary.strip()
                    else:
                        logger.warning("Fallback LLM not available")
                        
                except Exception as fallback_error:
                    logger.error(f"Fallback model also failed: {fallback_error}")
            
            # Final fallback: simple truncation
            logger.info(f"Using truncation fallback for {content_type} content")
            return content[:config_loader.get_content_summary_threshold()] + "... [truncated due to summarization failure]"
    
    @handle_errors("calculating tool token consumption", reraise=False)
    def _log_tools_token_stats(self):
        """Log token consumption statistics for tool descriptions and input schemas"""
        from mcp_modules.connector import MCPConnector
        
        # Calculate token consumption for all available tools
        stats = MCPConnector.estimate_tools_token_count(self.all_tools)
        
        logger.debug("=== Tool Description Token Statistics ===")
        logger.debug(f"Total tools: {stats['tool_count']}")
        logger.debug(f"Total tokens: {stats['total_tokens']}")
        logger.debug(f"Description tokens: {stats['description_tokens']}")
        logger.debug(f"Schema tokens: {stats['schema_tokens']}")
        logger.debug(f"Average tokens per tool: {stats['total_tokens'] // stats['tool_count'] if stats['tool_count'] > 0 else 0}")
        
        
        # Log top 5 tools with highest token consumption
        if stats['per_tool_tokens']:
            sorted_tools = sorted(
                stats['per_tool_tokens'].items(), 
                key=lambda x: x[1]['total'], 
                reverse=True
            )
            logger.debug("=== Top 5 Tools by Token Consumption ===")
            for i, (tool_name, tool_stats) in enumerate(sorted_tools[:5], 1):
                logger.debug(f"{i}. {tool_name}: {tool_stats['total']} tokens (description: {tool_stats['description']}, schema: {tool_stats['schema']})")
        
        logger.debug("========================")
    
    @handle_errors("compressing planning state", reraise=False)
    async def compress_planning_state(self, target_tokens: int = 3000) -> bool:
        """Compress prompt-facing planning state without touching judge-facing execution history."""
        if not self.planning_state:
            logger.info("No planning state to compress")
            return False

        planning_text = self._render_planning_state()
        original_tokens = len(planning_text) // 4

        if original_tokens <= target_tokens:
            logger.info(f"Planning state already within target ({original_tokens} <= {target_tokens} tokens)")
            return False

        logger.info(f"Starting LLM-based compression of planning_state: {original_tokens} tokens -> target {target_tokens} tokens")

        system_prompt = (
            "You compress structured planning state for a multi-round agent. Preserve exact tool names,"
            " important parameters, failures, counts, and key findings. Do not reintroduce omitted raw item lists."
        )
        user_prompt = f"""Compress the following planning state to approximately {target_tokens} tokens while preserving:
        1. Exact tool names and round ordering
        2. Important parameters and constraints discovered so far
        3. Key findings, counts, IDs/titles already retained in summaries
        4. Failures or dead ends the planner should avoid repeating

        PLANNING STATE TO COMPRESS:
        {planning_text}

        COMPRESSED PLANNING STATE:"""

        try:
            compressed_content = await self.llm.get_completion(
                system_prompt,
                user_prompt[:config_loader.get_user_prompt_max_length()],
                target_tokens
            )

            compressed_tokens = len(compressed_content) // 4
            if compressed_tokens < original_tokens:
                self.planning_state = [{
                    "type": "compressed_history",
                    "summary_text": compressed_content.strip()
                }]
                logger.info(
                    f"Planning-state compression successful: {original_tokens} -> {compressed_tokens} tokens "
                    f"({((original_tokens - compressed_tokens) / original_tokens * 100):.1f}% reduction)"
                )
                return True

            logger.warning("Planning-state LLM compression did not reduce token count, falling back to rule-based compression")
            return self._fallback_rule_based_planning_state_compression(target_tokens, original_tokens)

        except Exception as llm_error:
            logger.warning(f"Planning-state compression failed: {llm_error}, falling back to rule-based compression")
            return self._fallback_rule_based_planning_state_compression(target_tokens, original_tokens)

    @handle_errors("rule-based planning state compression fallback", reraise=False)
    def _fallback_rule_based_planning_state_compression(self, target_tokens: int, original_tokens: int) -> bool:
        """Fallback rule-based compression for prompt-facing planning state."""
        if not self.planning_state:
            return False

        keep_recent_entries = 6
        recent_entries = self.planning_state[-keep_recent_entries:]
        older_entries = self.planning_state[:-keep_recent_entries] if len(self.planning_state) > keep_recent_entries else []

        summary_parts = []
        if older_entries:
            round_numbers = sorted({
                entry.get('round') for entry in older_entries
                if isinstance(entry, dict) and entry.get('type') != 'compressed_history' and entry.get('round') is not None
            })
            successful_tools = sorted({
                entry.get('tool', 'unknown') for entry in older_entries
                if isinstance(entry, dict) and entry.get('type') != 'compressed_history' and entry.get('success')
            })
            failed_tools = sorted({
                entry.get('tool', 'unknown') for entry in older_entries
                if isinstance(entry, dict) and entry.get('type') != 'compressed_history' and not entry.get('success')
            })

            summary_parts.append(f"Compressed {len(older_entries)} earlier planning entries")
            if round_numbers:
                summary_parts.append(f"rounds {round_numbers[0]}-{round_numbers[-1]}")
            if successful_tools:
                summary_parts.append(f"successful tools: {', '.join(successful_tools[:12])}")
            if failed_tools:
                summary_parts.append(f"failed tools: {', '.join(failed_tools[:8])}")

        compressed_state = []
        if summary_parts:
            compressed_state.append({
                "type": "compressed_history",
                "summary_text": "; ".join(summary_parts)
            })
        compressed_state.extend(recent_entries)
        self.planning_state = compressed_state

        new_tokens = len(self._render_planning_state()) // 4
        logger.info(
            f"Rule-based planning-state compression completed: {original_tokens} -> {new_tokens} tokens "
            f"({((original_tokens - new_tokens) / original_tokens * 100):.1f}% reduction)"
        )
        return new_tokens < original_tokens

    @handle_errors("compressing accumulated information", reraise=False)
    async def compress_accumulated_information(self, target_tokens: int = 3000) -> bool:
        """
        Compress accumulated_information using LLM to reduce token usage
        
        Args:
            target_tokens: Target token count
            
        Returns:
            bool: Whether compression was successful
        """
        if not self.accumulated_information:
            logger.info("No accumulated information to compress")
            return False
        
        original_length = len(self.accumulated_information)
        original_tokens = original_length // 4
        
        if original_tokens <= target_tokens:
            logger.info(f"Accumulated information already within target ({original_tokens} <= {target_tokens} tokens)")
            return False
        
        logger.info(f"Starting LLM-based compression of accumulated_information: {original_tokens} tokens -> target {target_tokens} tokens")
        
        # Use LLM to compress the accumulated information intelligently
        system_prompt = "You are an expert information summarizer. Your task is to compress execution history while preserving all critical information and findings."
        
        user_prompt = f"""Please compress the following execution history to approximately {target_tokens} tokens while preserving:
        1. All key findings and results
        2. Important tool execution outcomes
        3. Critical information discovered
        4. Task progress and context
        EXECUTION HISTORY TO COMPRESS:
        {self.accumulated_information}
        COMPRESSED EXECUTION HISTORY:"""

        try:
            # Use LLM to compress - no context compression callback to avoid recursion
            compressed_content = await self.llm.get_completion(
                system_prompt, 
                user_prompt[:config_loader.get_user_prompt_max_length()],  # Limit input to prevent token issues
                target_tokens
            )
            
            # Validate compression result
            compressed_length = len(compressed_content)
            compressed_tokens = compressed_length // 4
            
            if compressed_tokens < original_tokens:
                self.accumulated_information = compressed_content.strip()
                logger.info(f"LLM compression successful: {original_tokens} -> {compressed_tokens} tokens ({((original_tokens - compressed_tokens) / original_tokens * 100):.1f}% reduction)")
                return True
            else:
                logger.warning("LLM compression did not reduce token count, falling back to rule-based compression")
                # Fall back to rule-based compression
                return self._fallback_rule_based_compression(target_tokens, original_tokens)
                
        except Exception as llm_error:
            logger.warning(f"LLM compression failed: {llm_error}, falling back to rule-based compression")
            return self._fallback_rule_based_compression(target_tokens, original_tokens)
    
    @handle_errors("rule-based compression fallback", reraise=False)
    def _fallback_rule_based_compression(self, target_tokens: int, original_tokens: int) -> bool:
        """Fallback rule-based compression when LLM compression fails"""
        rounds = self.accumulated_information.split("--- Summary of Round ")
        
        if len(rounds) <= 1:
            # Simple truncation compression
            target_chars = target_tokens * 4
            compressed_info = f"[Early execution history compressed for token limit]\n\n{self.accumulated_information[-target_chars:]}"
            self.accumulated_information = compressed_info
            
            new_length = len(self.accumulated_information)
            new_tokens = new_length // 4
            logger.info(f"Rule-based simple compression completed: {original_tokens} -> {new_tokens} tokens")
            return True
        
        # Smart round-based compression
        first_part = rounds[0]
        keep_recent_rounds = 2
        recent_rounds = rounds[-keep_recent_rounds:] if len(rounds) > keep_recent_rounds else rounds[1:]
        
        middle_rounds_count = len(rounds) - 1 - len(recent_rounds)
        if middle_rounds_count > 0:
            compressed_middle = f"[Rounds 2-{middle_rounds_count+1} compressed: Multiple tools executed successfully, information gathered and accumulated]"
        else:
            compressed_middle = ""
        
        compressed_parts = [first_part.strip()]
        if compressed_middle:
            compressed_parts.append(compressed_middle)
        
        for round_content in recent_rounds:
            if round_content.strip():
                compressed_parts.append("--- Summary of Round " + round_content)
        
        self.accumulated_information = "\n\n".join(compressed_parts)
        
        new_length = len(self.accumulated_information)
        new_tokens = new_length // 4
        
        # Further compression if still too long
        if new_tokens > target_tokens:
            target_chars = target_tokens * 4
            if len(self.accumulated_information) > target_chars:
                keep_start = target_chars // 2
                keep_end = target_chars // 2
                start_part = self.accumulated_information[:keep_start]
                end_part = self.accumulated_information[-keep_end:]
                self.accumulated_information = f"{start_part}\n\n[Middle content compressed for token limit]\n\n{end_part}"
                
                new_length = len(self.accumulated_information)
                new_tokens = new_length // 4
        
        logger.info(f"Rule-based compression completed: {original_tokens} -> {new_tokens} tokens ({((original_tokens - new_tokens) / original_tokens * 100):.1f}% reduction)")
        return True
