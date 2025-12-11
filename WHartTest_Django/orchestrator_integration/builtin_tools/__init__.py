"""
内置工具管理模块

提供 AI Agent 可调用的持久化工具，包括：
- Playwright 脚本管理工具（查询、查看、编辑、执行）
- 测试用例查询工具（未来扩展）

使用方式：
    from orchestrator_integration.builtin_tools import get_builtin_tools
    
    tools = get_builtin_tools(
        user_id=request.user.id,
        project_id=project_id,
        test_case_id=test_case_id  # 可选
    )
"""

from .playwright_tools import get_playwright_tools

import logging

logger = logging.getLogger('orchestrator_integration')


def get_builtin_tools(
    user_id: int,
    project_id: int,
    test_case_id: int = None,
) -> list:
    """
    获取所有内置工具
    
    Args:
        user_id: 当前用户 ID
        project_id: 当前项目 ID
        test_case_id: 关联的测试用例 ID（可选）
    
    Returns:
        LangChain 工具列表
    """
    tools = []
    
    # Playwright 脚本管理工具
    playwright_tools = get_playwright_tools(
        user_id=user_id,
        project_id=project_id,
        test_case_id=test_case_id,
    )
    tools.extend(playwright_tools)
    logger.info(f"[BuiltinTools] 加载 {len(playwright_tools)} 个 Playwright 工具")
    
    # 未来扩展：测试用例工具
    # testcase_tools = get_testcase_tools(user_id, project_id)
    # tools.extend(testcase_tools)
    
    return tools
