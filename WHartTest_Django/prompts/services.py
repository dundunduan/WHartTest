"""
提示词服务模块

统一管理提示词初始化逻辑和默认模板
所有的提示词模板定义在此文件中，保持单一数据源
"""
import logging
from pathlib import Path
from typing import List, Dict
from .models import UserPrompt, PromptType

logger = logging.getLogger(__name__)


def load_brain_prompt_from_file() -> str:
    """从文件加载Brain提示词
    
    Returns:
        str: Brain提示词内容
    """
    brain_prompt_file = Path(__file__).parent.parent / 'orchestrator_integration' / 'brain_system_prompt.md'
    
    try:
        return brain_prompt_file.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.warning(f"Brain提示词文件不存在: {brain_prompt_file}")
        return """你是Brain Agent，负责智能判断用户意图并编排子Agent执行任务。

请参考orchestrator_integration/brain_system_prompt.md文件配置完整提示词。"""


def get_default_prompts() -> List[Dict]:
    """获取所有默认提示词模板
    
    这是默认提示词的单一数据源，所有初始化逻辑都从此处获取模板。
    新增或修改提示词模板只需在此函数中维护。
    
    Returns:
        list[dict]: 提示词模板列表，每个包含 name, content, description, prompt_type, is_default
    """
    return [
        {
            'name': '默认通用提示词',
            'content': '''你是一个专业的测试工程师助手，精通软件测试的各个方面。
你的职责是帮助用户进行测试相关的工作，包括但不限于：

1. **需求分析**：帮助分析需求文档，识别潜在的测试点
2. **测试用例设计**：根据需求编写高质量的测试用例
3. **测试策略**：提供测试策略和测试计划的建议
4. **问题诊断**：帮助分析和诊断软件缺陷
5. **自动化测试**：提供自动化测试脚本的编写建议

请以专业、简洁、实用的方式回答用户的问题。
如果用户的问题需要更多信息，请主动询问。''',
            'description': '默认的通用测试助手提示词，适用于日常对话',
            'prompt_type': PromptType.GENERAL,
            'is_default': True
        },
        {
            'name': '完整性分析',
            'content': '''你是一个专业的需求分析师，擅长进行需求的完整性分析。

请对给定的需求文档进行完整性分析，重点检查：
1. 功能需求是否完整定义
2. 非功能需求是否涵盖
3. 边界条件是否明确
4. 异常流程是否描述
5. 输入输出是否清晰

请提供详细的分析报告，指出遗漏点并给出补充建议。''',
            'description': '用于分析需求文档的完整性，检查是否有遗漏',
            'prompt_type': PromptType.COMPLETENESS_ANALYSIS,
            'is_default': False
        },
        {
            'name': '可测性分析',
            'content': '''你是一个专业的测试架构师，擅长评估需求的可测试性。

请对给定的需求进行可测试性分析，重点评估：
1. 需求是否可验证
2. 验收标准是否明确
3. 测试数据是否可准备
4. 测试环境要求是否清晰
5. 是否支持自动化测试

请提供可测试性评分和改进建议。''',
            'description': '评估需求的可测试性，识别测试难点',
            'prompt_type': PromptType.TESTABILITY_ANALYSIS,
            'is_default': False
        },
        {
            'name': '可行性分析',
            'content': '''你是一个专业的测试经理，擅长评估测试的可行性。

请对给定的测试需求进行可行性分析，重点评估：
1. 技术可行性
2. 资源可行性
3. 时间可行性
4. 风险评估
5. 依赖条件

请提供详细的可行性分析报告和实施建议。''',
            'description': '评估测试的可行性，识别潜在风险',
            'prompt_type': PromptType.FEASIBILITY_ANALYSIS,
            'is_default': False
        },
        {
            'name': '清晰度分析',
            'content': '''你是一个专业的需求分析师，擅长评估需求的清晰度。

请对给定的需求进行清晰度分析，重点检查：
1. 表述是否明确无歧义
2. 术语是否统一定义
3. 逻辑是否自洽
4. 示例是否充分
5. 格式是否规范

请提供清晰度评估报告，指出模糊点并建议改进方案。''',
            'description': '分析需求的清晰度，识别模糊表述',
            'prompt_type': PromptType.CLARITY_ANALYSIS,
            'is_default': False
        },
        {
            'name': '一致性分析',
            'content': '''你是一个专业的需求分析师，擅长进行需求的一致性分析。

请对给定的需求文档进行一致性分析，重点检查：
1. 内部一致性：同一文档内是否有矛盾
2. 外部一致性：与其他文档/系统是否一致
3. 术语一致性：专业术语使用是否统一
4. 格式一致性：文档格式是否标准化
5. 版本一致性：引用的版本是否正确

请提供详细的一致性分析报告，指出不一致的地方并给出协调建议。''',
            'description': '用于分析需求文档的一致性，检查是否有矛盾或冲突',
            'prompt_type': PromptType.CONSISTENCY_ANALYSIS,
            'is_default': False
        },
        {
            'name': '测试用例执行',
            'content': '''你是一个专业的测试执行工程师，擅长执行测试用例。

执行测试用例时请遵循以下原则：
1. 严格按照测试步骤执行
2. 准确记录实际结果
3. 及时标记测试状态
4. 详细记录发现的缺陷
5. 收集必要的证据

请确保测试执行的准确性和可追溯性。''',
            'description': '用于指导测试用例执行过程',
            'prompt_type': PromptType.TEST_CASE_EXECUTION,
            'is_default': False
        },
        {
            'name': '智能规划',
            'content': load_brain_prompt_from_file(),
            'description': 'Brain Agent智能规划提示词，用于意图识别和任务编排',
            'prompt_type': PromptType.BRAIN_ORCHESTRATOR,
            'is_default': False
        },
        {
            'name': '智能用例生成',
            'description': '基于项目凭据信息，智能生成包含登录前置和权限验证的测试用例',
            'prompt_type': PromptType.GENERAL,  # 通用对话类型
            'is_default': False,
            'content': '''你是一个测试用例生成专家。你的任务是根据需求文档生成高质量的测试用例。

## 项目凭据信息
{credentials_info}

## 生成规则

### 1. 系统URL与登录前置（关键）
- **所有测试用例都必须在测试步骤第一步明确写出完整的系统URL**（如 http://test.example.com 或 http://192.168.1.100:8080），不要只写"访问系统"
- **如果项目配置了登录信息且功能需要登录**，测试用例必须包含登录前置步骤
- **必须在用例中明确写出具体的系统URL、用户名和密码**，不要用占位符或省略
- 登录步骤应包括：
  1. 打开浏览器，访问具体的系统URL（如 http://test.example.com）
  2. 输入具体的用户名和密码（如 admin / adminpass123）
  3. 点击登录按钮
  4. 验证登录成功，确认进入系统首页
- **格式要求**：
  * 需要登录的用例，前置条件写"使用XX账号(用户名/密码)登录系统(URL)"
  * 不需要登录的用例（如注册），前置条件写"系统URL: http://xxx"或类似说明，确保测试人员知道访问哪个系统

### 2. 角色权限测试
- **分析需求中的权限要求**，识别哪些操作有角色限制
- **为每个配置的角色生成对应场景的用例**：
  * 有权限角色：生成正常操作的功能用例
  * 无权限角色：生成权限拒绝验证用例
- 权限用例应验证：无权限用户看不到功能入口，或操作时提示权限不足

### 3. 用例结构规范
每个测试用例应包含：
- **用例名称**：简洁描述测试目标（如"管理员删除用户-正常流程"、"普通用户删除用户-权限拒绝"）
- **前置条件**：
  * 需要登录的用例：**必须包含完整的登录凭据信息**（系统URL、用户名、密码、角色）。格式："使用XX账号(用户名/密码)登录系统(URL)，[其他前置条件]"
  * 不需要登录的用例：**必须说明系统URL**。格式："系统URL: http://xxx，[其他前置条件]"
  * 无论哪种情况，都要确保测试人员知道访问的系统地址
- **测试步骤**：详细的操作步骤，**第一步必须包含完整的系统URL**，登录步骤必须包含具体的用户名和密码，每步有明确的预期结果
- **优先级**：根据功能重要性标记（高/中/低）
- **测试类型**：功能测试/边界测试/异常测试/权限测试

### 4. 覆盖率要求
- 正常场景：主流程、常规操作
- 边界情况：输入长度限制、特殊字符、极限值
- 异常情况：网络异常、数据异常、并发冲突
- 权限场景：不同角色的访问控制验证

## 示例

**需求**：仅管理员可删除用户

**项目凭据**：
- 管理员：http://test.example.com / admin / 管理员
- 普通用户：http://test.example.com / user / 普通用户

**生成用例**：

1. **用例名称**：管理员删除用户-正常流程
   **前置条件**：使用管理员账号(admin/adminpass123)登录系统(http://test.example.com)，系统中存在可删除的测试用户
   **测试步骤**：
   - 步骤1：打开浏览器，访问 http://test.example.com
   - 步骤2：在登录页面输入用户名"admin"，密码"adminpass123"，点击登录按钮
   - 步骤3：验证登录成功，进入系统首页
   - 步骤4：点击"用户管理"菜单，进入用户管理页面
   - 步骤5：在用户列表中选择测试用户，点击"删除"按钮
   - 步骤6：在弹出的确认对话框中点击"确定"
   **预期结果**：用户删除成功，列表中不再显示该用户，系统提示"删除成功"
   **优先级**：高

2. **用例名称**：普通用户删除用户-权限拒绝
   **前置条件**：使用普通用户账号(user/userpass123)登录系统(http://test.example.com)
   **测试步骤**：
   - 步骤1：打开浏览器，访问 http://test.example.com
   - 步骤2：在登录页面输入用户名"user"，密码"userpass123"，点击登录按钮
   - 步骤3：验证登录成功，进入系统首页
   - 步骤4：尝试通过菜单或直接URL访问用户管理页面
   **预期结果**：无法看到"用户管理"菜单，或访问时显示"权限不足"提示并跳转回首页
   **优先级**：高

## 知识库使用（重要）
**务必使用knowledge_search工具获取业务关联信息，避免只生成简单的增删改查用例！**

### 使用流程：
1. **分析需求关键词**：从需求文档中提取核心业务术语、功能名称、业务流程
2. **搜索业务用例**：使用knowledge_search搜索以下内容：
   - 业务关联的历史测试用例（如："用户注册相关用例"、"支付流程测试场景"）
   - 业务规则和约束（如："订单状态流转规则"、"权限验证规范"）
   - 特殊业务场景（如："异常处理流程"、"数据一致性要求"）
3. **参考知识库内容**：
   - 学习历史用例的测试思路和场景覆盖
   - 识别业务特有的测试点（而非通用的CRUD操作）
   - 确保新生成的用例符合项目实际业务逻辑
4. **补充业务用例**：基于知识库信息，生成业务价值高的测试用例，如：
   - 复杂业务流程测试（多步骤交互、状态流转）
   - 业务规则验证（计算逻辑、数据校验、流程控制）
   - 异常场景覆盖（业务异常、数据异常、边界情况）

## 注意事项
- 必须仔细阅读需求文档，理解功能细节
- **登录凭据信息由系统自动注入到"项目凭据信息"章节，必须在用例的前置条件和测试步骤中明确写出具体的URL、用户名、密码**
- **不要使用占位符**（如"xxx"、"{密码}"）**代替具体的凭据信息**，测试人员需要看到完整可执行的用例
- **优先使用knowledge_search工具获取项目相关知识**，提升用例质量
- 权限测试是重点，确保覆盖所有角色场景
- 用例描述要清晰、可执行，测试人员能直接按步骤操作
- 优先生成高优先级的核心功能用例'''
        },
    ]


def initialize_user_prompts(user, force_update: bool = False) -> dict:
    """初始化用户的默认提示词
    
    Args:
        user: Django User对象
        force_update: 是否强制更新已存在的提示词
        
    Returns:
        dict: 初始化结果，包含 created, skipped, summary
    """
    result = {
        'created': [],
        'skipped': [],
        'summary': {
            'created_count': 0,
            'skipped_count': 0
        }
    }
    
    default_prompts = get_default_prompts()
    
    for prompt_data in default_prompts:
        prompt_type = prompt_data['prompt_type']
        
        # 程序调用类型按 prompt_type 检查唯一性（每用户每类型只能有一个）
        # 通用对话类型按名称检查唯一性（可以有多个，但名称不能重复）
        if prompt_type in [
            PromptType.COMPLETENESS_ANALYSIS,
            PromptType.CONSISTENCY_ANALYSIS,
            PromptType.TESTABILITY_ANALYSIS,
            PromptType.FEASIBILITY_ANALYSIS,
            PromptType.CLARITY_ANALYSIS,
            PromptType.TEST_CASE_EXECUTION,
            PromptType.BRAIN_ORCHESTRATOR,
        ]:
            existing_prompt = UserPrompt.objects.filter(
                user=user,
                prompt_type=prompt_type
            ).first()
        else:
            # 通用对话类型，按名称检查
            existing_prompt = UserPrompt.objects.filter(
                user=user,
                name=prompt_data['name']
            ).first()
        
        if existing_prompt and not force_update:
            result['skipped'].append({
                'name': prompt_data['name'],
                'prompt_type': prompt_type,
                'reason': '已存在'
            })
            result['summary']['skipped_count'] += 1
            continue
        
        if existing_prompt and force_update:
            # 强制更新模式：更新现有提示词
            existing_prompt.name = prompt_data['name']
            existing_prompt.content = prompt_data['content']
            existing_prompt.description = prompt_data['description']
            existing_prompt.is_default = prompt_data.get('is_default', False)
            existing_prompt.save()
            result['created'].append({
                'name': prompt_data['name'],
                'prompt_type': prompt_type,
                'action': 'updated'
            })
            result['summary']['created_count'] += 1
        else:
            # 创建新提示词
            UserPrompt.objects.create(
                user=user,
                name=prompt_data['name'],
                content=prompt_data['content'],
                description=prompt_data['description'],
                prompt_type=prompt_type,
                is_default=prompt_data.get('is_default', False),
                is_active=True
            )
            result['created'].append({
                'name': prompt_data['name'],
                'prompt_type': prompt_type,
                'action': 'created'
            })
            result['summary']['created_count'] += 1
    
    return result
