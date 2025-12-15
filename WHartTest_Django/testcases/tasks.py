"""
测试用例执行的Celery异步任务
"""
import logging
import asyncio
import re
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from datetime import datetime
from typing import Dict, Any
from django.conf import settings
import os
import json
import uuid
import httpx
from rest_framework_simplejwt.tokens import RefreshToken

from .models import TestExecution, TestSuite, TestCaseResult, TestCase, ScriptExecution
from prompts.models import UserPrompt, PromptType
from asgiref.sync import sync_to_async
from .script_executor import execute_automation_script

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='testcases.execute_test_suite')
def execute_test_suite(self, execution_id):
    """
    执行测试套件的异步任务
    
    Args:
        execution_id: TestExecution实例的ID
        
    Returns:
        dict: 执行结果摘要
    """
    try:
        # 获取执行记录
        execution = TestExecution.objects.select_related('suite').get(id=execution_id)
        suite = execution.suite
        
        logger.info(f"开始执行测试套件: {suite.name} (ID: {suite.id})")
        
        # 更新执行状态为运行中
        execution.status = 'running'
        execution.started_at = timezone.now()
        execution.celery_task_id = self.request.id
        execution.save(update_fields=['status', 'started_at', 'celery_task_id', 'updated_at'])
        
        # 1. 获取套件中的所有测试用例
        testcases = suite.testcases.all().order_by('level', 'id')  # 按优先级排序
        
        # 2. 获取套件中的所有自动化脚本
        scripts = suite.automation_scripts.all().order_by('id')
        
        # 更新总数
        execution.total_count = testcases.count() + scripts.count()
        execution.save(update_fields=['total_count', 'updated_at'])
        
        # 收集所有待执行的任务
        all_tasks = []
        
        # 为每个测试用例创建结果记录
        for testcase in testcases:
            result = TestCaseResult.objects.create(
                execution=execution,
                testcase=testcase,
                status='pending'
            )
            all_tasks.append(result)
            
        # 为每个自动化脚本创建执行记录
        for script in scripts:
            script_exec = ScriptExecution.objects.create(
                script=script,
                test_execution=execution,
                executor=execution.executor,
                status='pending',
                browser_type='chromium'
            )
            all_tasks.append(script_exec)
        
        # 获取并发配置
        max_concurrent = suite.max_concurrent_tasks
        logger.info(f"并发配置: {max_concurrent} 个任务同时执行")
        
        # 使用asyncio执行并发测试
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _execute_tasks_concurrently(execution, all_tasks, max_concurrent)
            )
        finally:
            loop.close()
        
        # 更新执行记录为已完成
        execution.refresh_from_db()
        execution.status = 'completed' if execution.status != 'cancelled' else 'cancelled'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['status', 'completed_at', 'updated_at'])
        
        logger.info(f"测试套件执行完成: {suite.name}, "
                   f"通过: {execution.passed_count}, "
                   f"失败: {execution.failed_count}, "
                   f"错误: {execution.error_count}, "
                   f"跳过: {execution.skipped_count}")
        
        return {
            'execution_id': execution.id,
            'suite_name': suite.name,
            'status': execution.status,
            'total': execution.total_count,
            'passed': execution.passed_count,
            'failed': execution.failed_count,
            'skipped': execution.skipped_count,
            'error': execution.error_count,
            'pass_rate': execution.pass_rate,
            'duration': execution.duration
        }
        
    except TestExecution.DoesNotExist:
        error_msg = f"测试执行记录不存在: {execution_id}"
        logger.error(error_msg)
        return {'error': error_msg}
        
    except Exception as e:
        error_msg = f"执行测试套件时发生错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # 尝试更新执行状态为失败
        try:
            execution = TestExecution.objects.get(id=execution_id)
            execution.status = 'failed'
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'completed_at', 'updated_at'])
        except:
            pass
            
        return {'error': error_msg}


def execute_single_testcase(result: TestCaseResult):
    """
    执行单个测试用例 - 通过对话API驱动测试执行
    
    Args:
        result: TestCaseResult实例
    """
    logger.info(f"开始执行测试用例: {result.testcase.name} (ID: {result.testcase.id})")
    
    # 更新状态为执行中
    result.status = 'running'
    result.started_at = timezone.now()
    result.save(update_fields=['status', 'started_at', 'updated_at'])
    
    try:
        # 在新的事件循环中运行异步执行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_execute_testcase_via_chat_api(result))
        finally:
            loop.close()
        
        logger.info(f"测试用例执行成功: {result.testcase.name}")
        
    except Exception as e:
        error_msg = f"执行测试用例失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        result.status = 'error'
        result.error_message = error_msg
        result.completed_at = timezone.now()
        
        if result.started_at and result.completed_at:
            result.execution_time = (result.completed_at - result.started_at).total_seconds()
            
        result.save()
        raise


async def _execute_tasks_concurrently(execution, tasks_list, max_concurrent):
    """
    并发执行测试任务（包括用例和脚本）
    
    Args:
        execution: TestExecution实例
        tasks_list: TestCaseResult 或 ScriptExecution 列表
        max_concurrent: 最大并发数
    """
    import asyncio
    
    # 使用信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_with_semaphore(task_obj):
        """带信号量控制的执行函数"""
        async with semaphore:
            # 检查是否已取消
            current_execution = await sync_to_async(TestExecution.objects.get)(id=execution.id)
            if current_execution.status == 'cancelled':
                task_name = getattr(task_obj, 'testcase', getattr(task_obj, 'script', task_obj)).name
                logger.info(f"测试执行已取消，跳过任务: {task_name}")
                return
            
            try:
                # 更新状态为执行中
                task_obj.status = 'running'
                task_obj.started_at = timezone.now()
                await sync_to_async(task_obj.save)()
                
                # 根据任务类型调用不同的执行逻辑
                if isinstance(task_obj, TestCaseResult):
                    # 执行测试用例
                    await _execute_testcase_via_chat_api(task_obj)
                    task_name = task_obj.testcase.name
                elif isinstance(task_obj, ScriptExecution):
                    # 执行自动化脚本
                    await _execute_script_task(task_obj)
                    task_name = task_obj.script.name
                else:
                    raise ValueError(f"未知的任务类型: {type(task_obj)}")
                
                logger.info(f"任务执行成功: {task_name}")
                
                # 刷新状态
                await sync_to_async(task_obj.refresh_from_db)()
                
                # 统一状态映射
                status_map = {
                    'pass': 'pass', 'passed': 'pass',
                    'fail': 'fail', 'failed': 'fail',
                    'skip': 'skip', 'skipped': 'skip',
                    'error': 'error'
                }
                normalized_status = status_map.get(task_obj.status, 'error')
                
                # 更新统计（使用原子操作避免竞态）
                await sync_to_async(_update_execution_counts)(execution, normalized_status)
                
            except Exception as e:
                task_name = "Unknown"
                if hasattr(task_obj, 'testcase'):
                    task_name = task_obj.testcase.name
                elif hasattr(task_obj, 'script'):
                    task_name = task_obj.script.name
                    
                error_msg = f"并发执行任务失败: {str(e)}"
                logger.error(f"{error_msg} - {task_name}", exc_info=True)
                
                # 更新状态为错误
                task_obj.status = 'error'
                task_obj.error_message = error_msg
                task_obj.completed_at = timezone.now()
                
                if task_obj.started_at and task_obj.completed_at:
                    task_obj.execution_time = (task_obj.completed_at - task_obj.started_at).total_seconds()
                
                await sync_to_async(task_obj.save)()
                
                # 更新错误计数
                await sync_to_async(_update_execution_counts)(execution, 'error')
    
    # 创建所有任务
    async_tasks = [execute_with_semaphore(task) for task in tasks_list]
    
    # 并发执行所有任务
    await asyncio.gather(*async_tasks, return_exceptions=True)


@sync_to_async
def _execute_script_task(script_execution):
    """
    同步执行脚本任务的包装器
    """
    from .script_executor import ScriptExecutor
    
    script = script_execution.script
    
    # 创建执行器
    executor = ScriptExecutor(
        timeout_seconds=script.timeout_seconds,
        browser_type='chromium'
    )
    
    try:
        # 判断是否使用 pytest
        use_pytest = (
            script.script_type == 'playwright_python'
            and 'import pytest' in script.script_content
            and 'def test_' in script.script_content
        )
        
        # 执行脚本
        result = executor.execute_script(
            script_content=script.script_content,
            use_pytest=use_pytest,
            headless=script.headless,
            record_video=False # 暂时不开启录屏，或者从配置获取
        )
        
        # 更新执行记录
        script_execution.completed_at = result['completed_at']
        script_execution.execution_time = result['execution_time']
        script_execution.output = result['output']
        
        if result['success']:
            script_execution.status = 'pass'
        else:
            script_execution.status = 'fail'
            script_execution.error_message = result['error_message']
            script_execution.stack_trace = result['stack_trace']
        
        script_execution.screenshots = result['screenshots']
        script_execution.videos = result.get('videos', [])
        script_execution.save()
        
        # 清理临时目录
        executor.cleanup()
        
    except Exception as e:
        script_execution.status = 'error'
        script_execution.error_message = str(e)
        script_execution.completed_at = timezone.now()
        script_execution.save()
        executor.cleanup()
        raise


def _update_execution_counts(execution, status):
    """
    原子更新执行统计
    使用select_for_update避免并发写入冲突
    """
    with transaction.atomic():
        # 锁定当前执行记录
        exec_obj = TestExecution.objects.select_for_update().get(id=execution.id)
        
        if status == 'pass':
            exec_obj.passed_count += 1
        elif status == 'fail':
            exec_obj.failed_count += 1
        elif status == 'skip':
            exec_obj.skipped_count += 1
        elif status == 'error':
            exec_obj.error_count += 1
        
        exec_obj.save(update_fields=[
            'passed_count', 'failed_count', 'skipped_count',
            'error_count', 'updated_at'
        ])


@sync_to_async
def _get_testcase_steps(testcase):
    """获取测试用例步骤"""
    return list(testcase.steps.all().order_by('step_number'))

@sync_to_async
def _get_test_execution_prompt(executor):
    """获取测试用例执行提示词"""
    return UserPrompt.get_user_prompt_by_type(executor, PromptType.TEST_CASE_EXECUTION)

@sync_to_async
def _save_result(result: TestCaseResult):
    """异步安全地保存测试结果"""
    result.save()


def _normalize_media_url(url: str) -> str:
    """
    规范化媒体URL，确保正确添加MEDIA_URL前缀
    避免双重前缀问题（如 /media//media/...）
    
    Args:
        url: 原始URL路径
        
    Returns:
        规范化后的URL
    """
    if not url:
        return url
    
    # 如果已经是完整的HTTP URL，直接返回
    if url.startswith('http://') or url.startswith('https://'):
        return url
    
    # 规范化路径分隔符（将反斜杠替换为正斜杠）
    url = url.replace('\\', '/')
    
    media_url = settings.MEDIA_URL.rstrip('/')  # 通常是 '/media'
    
    # 如果已经以 MEDIA_URL 开头，直接返回
    if url.startswith(media_url + '/') or url.startswith(media_url):
        return url
    
    # 如果以 / 开头，去掉开头的 /
    if url.startswith('/'):
        url = url[1:]
    
    return f"{media_url}/{url}"


def _extract_test_result_json(response_text: str) -> dict | None:
    """
    从AI响应中提取测试结果JSON，支持多种格式
    
    支持的格式：
    1. 纯JSON
    2. ```json ... ``` 代码块
    3. ``` ... ``` 代码块
    4. 混合文本中的JSON对象
    
    Returns:
        解析后的JSON对象，或None
    """
    if not response_text or not response_text.strip():
        return None
    
    response_text = response_text.strip()
    
    # 预处理：处理可能的转义字符
    # 有些情况下响应中的换行符是字面量 \\n 而不是实际换行符
    normalized_text = response_text.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
    # 处理转义的引号 (如 \\\" -> ")
    normalized_text = normalized_text.replace('\\"', '"')
    
    # 方法1: 尝试提取 ```json ... ``` 代码块
    json_block_pattern = r'```json\s*([\s\S]*?)\s*```'
    for text in [normalized_text, response_text]:
        matches = re.findall(json_block_pattern, text, re.DOTALL)
        for match in matches:
            try:
                result = json.loads(match.strip())
                if isinstance(result, dict) and ('status' in result or 'steps' in result):
                    logger.debug(f"从 ```json 代码块提取JSON成功")
                    return result
            except json.JSONDecodeError:
                continue
    
    # 方法2: 尝试提取普通 ``` ... ``` 代码块
    code_block_pattern = r'```\s*([\s\S]*?)\s*```'
    for text in [normalized_text, response_text]:
        matches = re.findall(code_block_pattern, text, re.DOTALL)
        for match in matches:
            try:
                result = json.loads(match.strip())
                if isinstance(result, dict) and ('status' in result or 'steps' in result):
                    logger.debug(f"从普通代码块提取JSON成功")
                    return result
            except json.JSONDecodeError:
                continue
    
    # 方法3: 尝试直接解析整个响应
    for text in [normalized_text, response_text]:
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                logger.debug(f"直接解析响应为JSON成功")
                return result
        except json.JSONDecodeError:
            pass
    
    # 方法4: 尝试从文本中提取JSON对象 (寻找 { ... } 结构)
    # 从最后一个可能的JSON对象开始查找（通常结果在末尾）
    brace_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    for text in [normalized_text, response_text]:
        matches = re.findall(brace_pattern, text)
        for match in reversed(matches):  # 从最后一个开始尝试
            try:
                result = json.loads(match)
                if isinstance(result, dict) and ('status' in result or 'steps' in result):
                    logger.debug(f"从大括号结构提取JSON成功")
                    return result
            except json.JSONDecodeError:
                continue
    
    # 方法5: 更复杂的嵌套JSON提取
    # 找到所有的 { 开始位置，然后尝试匹配到对应的 }
    for text in [normalized_text, response_text]:
        start_positions = [i for i, c in enumerate(text) if c == '{']
        for start in reversed(start_positions):  # 从最后一个开始
            brace_count = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            candidate = text[start:i+1]
                            result = json.loads(candidate)
                            if isinstance(result, dict) and ('status' in result or 'steps' in result):
                                logger.debug(f"从嵌套结构提取JSON成功")
                                return result
                        except json.JSONDecodeError:
                            break  # 这个开始位置不行，尝试下一个
                        break
    
    return None

async def _execute_testcase_via_chat_api(result: TestCaseResult):
    """通过 Agent Loop SSE API 执行测试用例"""
    # 使用thread_sensitive=False避免死锁
    execution = await sync_to_async(lambda: result.execution, thread_sensitive=False)()
    testcase = await sync_to_async(lambda: result.testcase, thread_sensitive=False)()
    executor = await sync_to_async(lambda: execution.executor, thread_sensitive=False)()
    project = await sync_to_async(lambda: testcase.project, thread_sensitive=False)()
    # 获取是否生成脚本的配置
    generate_playwright_script = await sync_to_async(
        lambda: execution.generate_playwright_script, thread_sensitive=False
    )()

    # 调试日志：打印脚本生成配置
    logger.info(f"测试执行 ID: {execution.id}, 生成脚本配置: {generate_playwright_script}")

    if not executor or not project:
        raise Exception("无法获取执行人或项目信息")
    
    execution_log = []
    screenshots = []
    
    try:
        # 1. 获取测试用例执行提示词
        prompt = await _get_test_execution_prompt(executor)
        if not prompt:
            raise Exception("未找到测试用例执行提示词，请先初始化系统提示词")
        
        logger.info(f"使用测试执行提示词: {prompt.name}")
        execution_log.append(f"✓ 加载测试执行提示词: {prompt.name}")
        if generate_playwright_script:
            execution_log.append("✓ 已启用脚本生成模式")
        
        # 2. 获取测试步骤
        steps = await _get_testcase_steps(testcase)
        if not steps:
            raise Exception("测试用例没有定义执行步骤")
        
        # 3. 格式化测试步骤信息
        steps_text = ""
        for step in steps:
            steps_text += f"{step.step_number}. {step.description}\n   预期结果: {step.expected_result}\n"
        
        # 4. 格式化提示词，填充测试用例信息
        from string import Template
        prompt_template = Template(prompt.content)
        formatted_prompt = prompt_template.safe_substitute(
            project_id=project.id,
            testcase_id=testcase.id,
            testcase_name=testcase.name,
            precondition=testcase.precondition or "无",
            steps=steps_text.strip()
        )
        
        logger.info(f"格式化后的提示词长度: {len(formatted_prompt)} 字符")
        execution_log.append(f"✓ 准备执行 {len(steps)} 个测试步骤")
        
        # 5. 构造 Agent Loop API 请求
        api_url = f"{settings.BASE_URL}/api/orchestrator/agent-loop/" if hasattr(settings, 'BASE_URL') else "http://localhost:8000/api/orchestrator/agent-loop/"
        
        # 生成唯一的会话ID
        session_id = f"test_exec_{execution.id}_{testcase.id}_{result.id}_{uuid.uuid4().hex[:8]}"
        
        request_data = {
            "message": formatted_prompt,
            "session_id": session_id,
            "project_id": str(project.id),
            "prompt_id": str(prompt.id),
            "use_knowledge_base": False,
            "generate_playwright_script": generate_playwright_script,
            "test_case_id": testcase.id
        }
        
        logger.info(f"调用 Agent Loop API: {api_url}")
        logger.info(f"会话ID: {session_id}")
        execution_log.append(f"✓ 开始与AI测试引擎通信...")
        
        # 6. 生成认证令牌并调用 Agent Loop SSE API
        def generate_token():
            refresh = RefreshToken.for_user(executor)
            return str(refresh.access_token)
        
        access_token = await sync_to_async(generate_token)()
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        }
        
        # 收集 SSE 流式响应
        final_response = ""
        current_step_response = ""  # 当前步骤的响应内容
        step_count = 0
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                'POST',
                api_url,
                json=request_data,
                headers=headers
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith('data: '):
                        continue
                    
                    try:
                        data_str = line[6:]  # 去掉 'data: ' 前缀
                        if data_str == '[DONE]':
                            break
                        
                        data = json.loads(data_str)
                        event_type = data.get('type', '')
                        
                        if event_type == 'step_start':
                            step_count += 1
                            current_step_response = ""  # 重置当前步骤响应
                            execution_log.append(f"\n🔄 AI执行步骤 {step_count}")
                        
                        elif event_type == 'stream':
                            # 流式响应：每个事件包含一小段文本
                            stream_data = data.get('data', '')
                            if stream_data:
                                final_response += stream_data
                                current_step_response += stream_data
                        
                        elif event_type == 'content':
                            content = data.get('content', '')
                            if content:
                                final_response += content
                        
                        elif event_type == 'message':
                            # Agent Loop 的 message 事件包含 AI 的响应（思考过程）
                            msg_data = data.get('data', '')
                            if msg_data:
                                final_response += msg_data
                                # 显示 AI 的说明（前150字符）
                                short_msg = msg_data[:150].replace('\n', ' ').strip()
                                if len(msg_data) > 150:
                                    short_msg += '...'
                                if short_msg:
                                    execution_log.append(f"   💬 {short_msg}")
                        
                        elif event_type == 'tool_call':
                            tool_name = data.get('name', data.get('tool', ''))
                            tool_args = data.get('arguments', data.get('args', ''))
                            if tool_name:
                                execution_log.append(f"   🔧 调用工具: {tool_name}")
                            if tool_args and isinstance(tool_args, str) and len(tool_args) > 0:
                                # 只显示参数的前100个字符
                                short_args = tool_args[:100] + '...' if len(tool_args) > 100 else tool_args
                                execution_log.append(f"      参数: {short_args}")
                        
                        elif event_type == 'tool_start':
                            # 工具开始执行
                            tool_name = data.get('name', data.get('tool', ''))
                            if tool_name:
                                execution_log.append(f"   🔧 调用工具: {tool_name}")
                        
                        elif event_type == 'tool_result':
                            # 工具执行结果
                            result_summary = data.get('summary', '')
                            if result_summary:
                                # 只显示结果摘要的前150字符
                                short_result = result_summary[:150].replace('\n', ' ')
                                if len(result_summary) > 150:
                                    short_result += '...'
                                execution_log.append(f"   🔧 工具结果: {short_result}")
                        
                        elif event_type == 'stream_end':
                            # 流式响应结束，输出当前步骤的响应摘要
                            if current_step_response.strip():
                                summary = current_step_response.strip()[:200].replace('\n', ' ')
                                if len(current_step_response.strip()) > 200:
                                    summary += '...'
                                execution_log.append(f"   📝 {summary}")
                        
                        elif event_type == 'step_end' or event_type == 'step_complete':
                            # 步骤完全结束信号，tool_result已显示工具结果，此处不再重复
                            pass
                        
                        elif event_type == 'final':
                            final_response = data.get('content', final_response)
                        
                        elif event_type == 'ai':
                            # AI消息事件，检查是否是最终响应
                            content = data.get('content', '')
                            agent_type = data.get('agent_type', '')
                            if agent_type == 'final' and content:
                                # 这是最终AI响应，包含测试结果JSON
                                final_response = content
                                logger.info(f"收到最终AI响应, 长度: {len(content)}")
                            elif content:
                                # 普通AI响应，累加到final_response
                                final_response += content
                        
                        elif event_type == 'error':
                            error_msg = data.get('message', '未知错误')
                            execution_log.append(f"   ❌ 错误: {error_msg}")
                            raise Exception(error_msg)
                    
                    except json.JSONDecodeError:
                        continue
        
        logger.info(f"Agent Loop 执行完成，共 {step_count} 个步骤")
        
        # 7. 尝试从最终响应中提取JSON格式的测试结果
        if final_response:
            logger.debug(f"最终响应前100字符: {final_response[:100] if len(final_response) > 100 else final_response}")
            logger.debug(f"最终响应是否包含```json: {'```json' in final_response}")
        test_result_json = _extract_test_result_json(final_response)
        if not test_result_json:
            logger.warning(f"无法从AI响应中提取JSON, 响应长度: {len(final_response) if final_response else 0}")
            if final_response:
                logger.warning(f"响应内容(截断): {final_response[:500] if len(final_response) > 500 else final_response}")
            execution_log.append(f"⚠ AI响应格式不符合预期，分析响应内容")
            # 将实际响应内容记录到执行日志中，方便排查
            truncated = final_response[:1000] if final_response and len(final_response) > 1000 else final_response
            execution_log.append(f"实际响应: {truncated or '(无响应)'}")
        
        # 8. 根据解析结果更新TestCaseResult
        if test_result_json:
            final_status = test_result_json.get('status', 'fail')
            summary = test_result_json.get('summary', '')
            step_results = test_result_json.get('steps', [])
            
            result.status = 'pass' if final_status == 'pass' else 'fail'
            
            execution_log.append(f"\n{'='*50}")
            execution_log.append(f"测试结果: {final_status.upper()}")
            execution_log.append(f"总结: {summary}")
            execution_log.append(f"{'='*50}\n")
            
            for step_result in step_results:
                step_num = step_result.get('step_number', 0)
                step_desc = step_result.get('description', '')
                step_status = step_result.get('status', 'unknown')
                step_error = step_result.get('error')
                
                status_icon = "✓" if step_status == 'pass' else "✗"
                execution_log.append(f"[步骤 {step_num}] {status_icon} {step_desc}")
                
                if step_error:
                    execution_log.append(f"  错误: {step_error}")
        else:
            # 没有结构化JSON，分析响应内容判断结果
            has_error = 'error' in final_response.lower() or 'fail' in final_response.lower() or '失败' in final_response
            result.status = 'fail' if has_error else 'pass'
            
            execution_log.append(f"\n{'='*50}")
            execution_log.append(f"测试完成 - 状态: {'失败' if has_error else '通过'}")
            execution_log.append(f"{'='*50}\n")
        
        # 获取测试用例的截图
        try:
            testcase_screenshots = await sync_to_async(
                lambda: list(testcase.screenshots.filter(
                    step_number__isnull=False
                ).order_by('step_number').values_list('screenshot', flat=True))
            )()
            
            if testcase_screenshots:
                screenshots = [_normalize_media_url(url) for url in testcase_screenshots]
                logger.info(f"从测试用例获取到 {len(screenshots)} 个截图URL")
        except Exception as e:
            logger.warning(f"获取测试用例截图失败: {e}")
        
        if result.status == 'running':
            result.status = 'pass'
            execution_log.append("\n✓ 所有步骤执行完成")
        
        # 清理MCP会话
        try:
            from mcp_tools.persistent_client import mcp_session_manager
            await mcp_session_manager.cleanup_user_session(
                user_id=str(executor.id),
                project_id=str(project.id),
                session_id=session_id
            )
            logger.info(f"已清理MCP会话: {session_id}")
            execution_log.append(f"✓ 已清理浏览器会话资源")
        except Exception as e:
            logger.warning(f"清理MCP会话失败: {e}")
        
    except httpx.HTTPError as e:
        error_msg = f"调用 Agent Loop API 失败: {str(e)}"
        execution_log.append(f"\n✗ {error_msg}")
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)
    
    except Exception as e:
        error_msg = f"执行过程异常: {str(e)}"
        execution_log.append(f"\n✗ {error_msg}")
        logger.error(error_msg, exc_info=True)
        raise
    
    finally:
        result.execution_log = "\n".join(execution_log)
        result.screenshots = screenshots
        result.completed_at = timezone.now()
        
        if result.started_at and result.completed_at:
            result.execution_time = (result.completed_at - result.started_at).total_seconds()
        
        await _save_result(result)


@shared_task(name='testcases.cancel_test_execution')
def cancel_test_execution(execution_id):
    """
    取消测试执行
    
    Args:
        execution_id: TestExecution实例的ID
    """
    try:
        execution = TestExecution.objects.get(id=execution_id)
        
        if execution.status in ['pending', 'running']:
            execution.status = 'cancelled'
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'completed_at', 'updated_at'])
            
            # 取消所有pending状态的测试用例结果
            execution.results.filter(status='pending').update(
                status='skip',
                completed_at=timezone.now()
            )
            
            # 取消所有pending状态的脚本执行结果
            execution.script_results.filter(status='pending').update(
                status='cancelled',
                completed_at=timezone.now()
            )
            
            logger.info(f"测试执行已取消: {execution_id}")
            return {'success': True, 'message': '测试执行已取消'}
        else:
            return {'success': False, 'message': f'无法取消状态为 {execution.status} 的执行'}
            
    except TestExecution.DoesNotExist:
        return {'success': False, 'message': '测试执行记录不存在'}
    except Exception as e:
        logger.error(f"取消测试执行失败: {str(e)}", exc_info=True)
        return {'success': False, 'message': str(e)}