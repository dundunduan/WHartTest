<template>
  <div class="automation-script-management">
    <a-page-header title="自动化用例管理" subtitle="管理 AI 生成的 Playwright 自动化测试脚本" />

    <a-card class="filter-card">
      <div class="filter-row">
        <a-space wrap>
          <a-select
            v-model="filterStatus"
            placeholder="脚本状态"
            allow-clear
            style="width: 150px"
            @change="fetchScripts"
          >
            <a-option value="active">启用</a-option>
            <a-option value="draft">草稿</a-option>
            <a-option value="deprecated">已废弃</a-option>
          </a-select>
          <a-select
            v-model="filterSource"
            placeholder="来源"
            allow-clear
            style="width: 150px"
            @change="fetchScripts"
          >
            <a-option value="ai_generated">AI 生成</a-option>
            <a-option value="recorded">录制生成</a-option>
            <a-option value="manual">手动编写</a-option>
          </a-select>
          <a-input-search
            v-model="searchKeyword"
            placeholder="搜索脚本名称"
            style="width: 200px"
            @search="fetchScripts"
          />
        </a-space>
        <a-button type="primary" @click="fetchScripts">
          <template #icon><icon-refresh /></template>
          刷新
        </a-button>
      </div>
    </a-card>

    <a-card class="table-card">
      <a-table
        :data="scripts"
        :loading="loading"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #columns>
          <a-table-column title="ID" data-index="id" :width="70" align="center" />
          <a-table-column title="脚本名称" data-index="name" :width="250">
            <template #cell="{ record }">
              <a-link @click="showDetail(record)">{{ record.name }}</a-link>
            </template>
          </a-table-column>
          <a-table-column title="关联用例" data-index="test_case_name" :width="200" />
          <a-table-column title="类型" data-index="script_type" :width="120">
            <template #cell="{ record }">
              <a-tag color="blue">{{ getScriptTypeLabel(record.script_type) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="来源" data-index="source" :width="100">
            <template #cell="{ record }">
              <a-tag :color="getSourceColor(record.source)">
                {{ getSourceLabel(record.source) }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="状态" data-index="status" :width="80">
            <template #cell="{ record }">
              <a-badge :status="getStatusBadge(record.status)" :text="getStatusLabel(record.status)" />
            </template>
          </a-table-column>
          <a-table-column title="版本" data-index="version" :width="60" align="center">
            <template #cell="{ record }">v{{ record.version }}</template>
          </a-table-column>
          <a-table-column title="最近执行" data-index="latest_status" :width="100">
            <template #cell="{ record }">
              <template v-if="record.latest_status">
                <a-tag :color="getExecutionStatusColor(record.latest_status)">
                  {{ getExecutionStatusLabel(record.latest_status) }}
                </a-tag>
              </template>
              <span v-else class="text-gray">未执行</span>
            </template>
          </a-table-column>
          <a-table-column title="创建时间" data-index="created_at" :width="160">
            <template #cell="{ record }">
              {{ formatTime(record.created_at) }}
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="180" fixed="right">
            <template #cell="{ record }">
              <a-space>
                <a-button type="text" size="small" @click="showDetail(record)">
                  <icon-eye />
                </a-button>
                <a-dropdown trigger="hover">
                  <a-button
                    type="text"
                    size="small"
                    :loading="executingId === record.id"
                  >
                    <icon-play-arrow />
                    <icon-down style="margin-left: 2px; font-size: 10px;" />
                  </a-button>
                  <template #content>
                    <a-doption @click="executeScript(record, true, false)">
                      <icon-eye-invisible style="margin-right: 6px;" />
                      快速执行（无头）
                    </a-doption>
                    <a-doption @click="executeScript(record, true, true)">
                      <icon-video-camera style="margin-right: 6px;" />
                      录屏执行（无头+录屏）
                    </a-doption>
                    <a-doption @click="executeScript(record, false, false)">
                      <icon-desktop style="margin-right: 6px;" />
                      调试执行（有头可视）
                    </a-doption>
                  </template>
                </a-dropdown>
                <a-popconfirm
                  content="确定要删除此脚本吗？"
                  @ok="deleteScript(record.id)"
                >
                  <a-button type="text" size="small" status="danger">
                    <icon-delete />
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>

    <!-- 脚本详情抽屉 -->
    <a-drawer
      v-model:visible="detailVisible"
      :title="currentScript?.name || '脚本详情'"
      :width="800"
      :footer="false"
    >
      <template v-if="currentScript">
        <a-descriptions :column="2" bordered>
          <a-descriptions-item label="脚本名称">{{ currentScript.name }}</a-descriptions-item>
          <a-descriptions-item label="版本">v{{ currentScript.version }}</a-descriptions-item>
          <a-descriptions-item label="关联用例">{{ currentScript.test_case_name }}</a-descriptions-item>
          <a-descriptions-item label="脚本类型">{{ getScriptTypeLabel(currentScript.script_type) }}</a-descriptions-item>
          <a-descriptions-item label="来源">{{ getSourceLabel(currentScript.source) }}</a-descriptions-item>
          <a-descriptions-item label="状态">{{ getStatusLabel(currentScript.status) }}</a-descriptions-item>
          <a-descriptions-item label="目标URL" :span="2">{{ currentScript.target_url || '未指定' }}</a-descriptions-item>
          <a-descriptions-item label="描述" :span="2">{{ currentScript.description || '无' }}</a-descriptions-item>
        </a-descriptions>

        <a-divider>脚本代码</a-divider>
        <div class="code-container">
          <pre><code>{{ currentScript.script_content }}</code></pre>
        </div>

        <a-divider>执行历史</a-divider>
        <a-table
          :data="currentScript.executions || []"
          :loading="executionsLoading"
          size="small"
          :expandable="{ width: 50 }"
        >
          <template #columns>
            <a-table-column title="状态" data-index="status" :width="80">
              <template #cell="{ record }">
                <a-tag :color="getExecutionStatusColor(record.status)">
                  {{ getExecutionStatusLabel(record.status) }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="执行时间" data-index="created_at" :width="160">
              <template #cell="{ record }">{{ formatTime(record.created_at) }}</template>
            </a-table-column>
            <a-table-column title="耗时" data-index="execution_time" :width="80">
              <template #cell="{ record }">
                {{ record.execution_time ? `${record.execution_time.toFixed(2)}s` : '-' }}
              </template>
            </a-table-column>
            <a-table-column title="执行人" data-index="executor_detail">
              <template #cell="{ record }">
                {{ record.executor_detail?.username || '-' }}
              </template>
            </a-table-column>
          </template>
          <!-- 展开行显示详细报告 -->
          <template #expand-row="{ record }">
            <div class="execution-detail">
              <template v-if="record.error_message">
                <div class="detail-section error">
                  <div class="detail-label">❌ 错误信息</div>
                  <pre class="detail-content">{{ record.error_message }}</pre>
                </div>
              </template>
              <template v-if="record.stack_trace">
                <div class="detail-section">
                  <div class="detail-label">堆栈跟踪</div>
                  <pre class="detail-content stack-trace">{{ record.stack_trace }}</pre>
                </div>
              </template>
              <template v-if="record.output">
                <div class="detail-section">
                  <div class="detail-label">输出日志</div>
                  <pre class="detail-content">{{ record.output }}</pre>
                </div>
              </template>
              <template v-if="record.screenshots && record.screenshots.length > 0">
                <div class="detail-section">
                  <div class="detail-label">截图 ({{ record.screenshots.length }})</div>
                  <a-image-preview-group infinite>
                    <div class="screenshots">
                      <a-image 
                        v-for="(screenshot, idx) in record.screenshots" 
                        :key="idx"
                        :src="`/media/${screenshot}`"
                        width="120"
                        height="80"
                        fit="cover"
                        :preview-props="{ actionsLayout: ['zoomIn', 'zoomOut', 'rotateLeft', 'rotateRight', 'originalSize'] }"
                      />
                    </div>
                  </a-image-preview-group>
                </div>
              </template>
              <template v-if="record.videos && record.videos.length > 0">
                <div class="detail-section">
                  <div class="detail-label">🎬 录屏 ({{ record.videos.length }})</div>
                  <div class="videos">
                    <video 
                      v-for="(video, idx) in record.videos" 
                      :key="idx"
                      :src="`/media/${video}`"
                      controls
                      class="video-player"
                    />
                  </div>
                </div>
              </template>
              <template v-if="!record.error_message && !record.output && !record.stack_trace && (!record.screenshots || record.screenshots.length === 0) && (!record.videos || record.videos.length === 0)">
                <div class="no-detail">暂无详细信息</div>
              </template>
            </div>
          </template>
        </a-table>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Message } from '@arco-design/web-vue';
import { 
  IconRefresh, IconEye, IconPlayArrow, IconDelete, IconDown, IconEyeInvisible, IconVideoCamera, IconDesktop
} from '@arco-design/web-vue/es/icon';
import { useProjectStore } from '@/store/projectStore';
import request from '@/utils/request';

interface AutomationScript {
  id: number;
  name: string;
  test_case: number;
  test_case_name: string;
  script_type: string;
  source: string;
  status: string;
  version: number;
  target_url: string;
  description: string;
  script_content: string;
  created_at: string;
  latest_status: string | null;
  executions?: any[];
}

const projectStore = useProjectStore();
const loading = ref(false);
const scripts = ref<AutomationScript[]>([]);
const searchKeyword = ref('');
const filterStatus = ref<string | undefined>();
const filterSource = ref<string | undefined>();
const executingId = ref<number | null>(null);

// 详情抽屉
const detailVisible = ref(false);
const currentScript = ref<AutomationScript | null>(null);
const executionsLoading = ref(false);

// 分页
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showTotal: true,
  showJumper: true,
});

// 获取脚本列表
const fetchScripts = async () => {
  loading.value = true;
  try {
    const params: any = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
    };
    
    if (projectStore.currentProjectId) {
      params.project_id = projectStore.currentProjectId;
    }
    if (filterStatus.value) params.status = filterStatus.value;
    if (filterSource.value) params.source = filterSource.value;
    if (searchKeyword.value) params.search = searchKeyword.value;
    
    const response = await request.get('/automation-scripts/', { params });
    // 响应拦截器会将后端的 { status, data: [...] } 转换为 { data: [...] }
    scripts.value = response.data.data || response.data.results || [];
    pagination.value.total = response.data.data?.length || response.data.count || scripts.value.length;
  } catch (error: any) {
    Message.error(error.message || '获取脚本列表失败');
  } finally {
    loading.value = false;
  }
};

// 分页变化
const handlePageChange = (page: number) => {
  pagination.value.current = page;
  fetchScripts();
};

// 显示详情
const showDetail = async (script: AutomationScript) => {
  currentScript.value = script;
  detailVisible.value = true;
  
  // 加载完整脚本信息和执行历史
  executionsLoading.value = true;
  try {
    const [scriptRes, execRes] = await Promise.all([
      request.get(`/automation-scripts/${script.id}/`),
      request.get(`/automation-scripts/${script.id}/executions/`)
    ]);
    // 响应拦截器会将后端的 { data: {...} } 解包
    const scriptData = scriptRes.data.data || scriptRes.data;
    const execData = execRes.data.data || execRes.data.results || execRes.data || [];
    currentScript.value = {
      ...scriptData,
      executions: execData
    };
  } catch (error) {
    console.error('加载脚本详情失败:', error);
  } finally {
    executionsLoading.value = false;
  }
};

// 执行脚本
const executeScript = async (script: AutomationScript, headless: boolean = true, recordVideo: boolean = false) => {
  executingId.value = script.id;
  const modeText = recordVideo ? '录屏模式' : '快速模式';
  try {
    await request.post(`/automation-scripts/${script.id}/execute/`, {
      headless: headless,
      record_video: recordVideo
    });
    Message.success(`脚本执行已启动（${modeText}）`);
    // 刷新列表以显示最新执行状态
    fetchScripts();
  } catch (error: any) {
    Message.error(error.response?.data?.error || '执行脚本失败');
  } finally {
    executingId.value = null;
  }
};

// 删除脚本
const deleteScript = async (id: number) => {
  try {
    await request.delete(`/automation-scripts/${id}/`);
    Message.success('脚本已删除');
    fetchScripts();
  } catch (error: any) {
    Message.error(error.message || '删除失败');
  }
};

// 格式化时间
const formatTime = (time: string) => {
  if (!time) return '-';
  return new Date(time).toLocaleString('zh-CN');
};

// 标签映射
const getScriptTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    'playwright_python': 'Playwright Python',
    'playwright_javascript': 'Playwright JS',
  };
  return map[type] || type;
};

const getSourceLabel = (source: string) => {
  const map: Record<string, string> = {
    'ai_generated': 'AI 生成',
    'recorded': '录制',
    'manual': '手动',
  };
  return map[source] || source;
};

const getSourceColor = (source: string) => {
  const map: Record<string, string> = {
    'ai_generated': 'green',
    'recorded': 'blue',
    'manual': 'gray',
  };
  return map[source] || 'gray';
};

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    'active': '启用',
    'draft': '草稿',
    'deprecated': '已废弃',
  };
  return map[status] || status;
};

const getStatusBadge = (status: string) => {
  const map: Record<string, 'success' | 'warning' | 'danger'> = {
    'active': 'success',
    'draft': 'warning',
    'deprecated': 'danger',
  };
  return map[status] || 'default';
};

const getExecutionStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    'pending': '等待中',
    'running': '执行中',
    'passed': '通过',
    'failed': '失败',
    'error': '错误',
    'cancelled': '已取消',
  };
  return map[status] || status;
};

const getExecutionStatusColor = (status: string) => {
  const map: Record<string, string> = {
    'pending': 'gray',
    'running': 'blue',
    'passed': 'green',
    'failed': 'red',
    'error': 'orange',
    'cancelled': 'gray',
  };
  return map[status] || 'gray';
};

onMounted(() => {
  fetchScripts();
});
</script>

<style scoped>
.automation-script-management {
  padding: 20px;
}

.filter-card {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-card {
  margin-bottom: 16px;
}

.text-gray {
  color: #86909c;
}

.code-container {
  background: #f5f5f5;
  border-radius: 4px;
  padding: 16px;
  max-height: 400px;
  overflow: auto;
}

.code-container pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.code-container code {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
}

/* 执行报告详情样式 */
.execution-detail {
  padding: 12px 16px;
  background: #fafafa;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-section.error .detail-content {
  color: #f53f3f;
  background: #fff1f0;
  border-color: #ffd6d6;
}

.detail-label {
  font-weight: 500;
  margin-bottom: 4px;
  color: #1d2129;
}

.detail-content {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 8px 12px;
  margin: 0;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
}

.detail-content.stack-trace {
  color: #86909c;
  font-size: 11px;
}

.screenshots {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.screenshots :deep(.arco-image) {
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  cursor: pointer;
}

.screenshots :deep(.arco-image:hover) {
  border-color: rgb(var(--primary-6));
}

.videos {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.video-player {
  max-width: 400px;
  max-height: 300px;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
}

.no-detail {
  color: #86909c;
  text-align: center;
  padding: 16px;
}
</style>
