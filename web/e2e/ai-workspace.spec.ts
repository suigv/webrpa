import { expect, test } from '@playwright/test';

const historyItem = {
  draft_id: 'draft-ai-1',
  display_name: 'X 登录补链路',
  status: 'needs_attention',
  updated_at: '2026-03-25T10:00:00Z',
  app_id: 'x',
  account: 'demo@example.com',
  last_task_id: 'task-ai-1',
  can_replay: true,
  can_edit: true,
  can_save: true,
  workflow_draft: {
    draft_id: 'draft-ai-1',
    display_name: 'X 登录补链路',
    status: 'needs_attention',
    success_count: 1,
    success_threshold: 3,
    can_continue: true,
    can_distill: false,
    message: '本次执行停在验证码前，已保留可复用上下文。',
    declarative_binding: {
      summary: 'X 登录（login）：准备登录流程 -> 判断登录状态 -> 收尾完成',
      script_count: 1,
      script_title: 'X 登录',
      current_stage: {
        stage_title: '判断登录状态',
      },
    },
    latest_failure_advice: {
      summary: '先确认账号密码是否可用，再决定是否需要人工接管验证码。',
      suggestions: ['补充验证码处理要求', '强调首页成功判定'],
      suggested_prompt: '如果出现验证码先暂停并等待人工处理',
    },
    distill_assessment: {
      latest_qualification: 'replayable',
      success_count: 1,
      success_threshold: 3,
    },
    latest_run_asset: {
      terminal_message: '执行停在验证码前',
      retained_value: ['draft_memory', 'trace_context'],
      learned_assets: {
        observed_state_ids: ['login_form', 'captcha_gate'],
      },
      memory_summary: {
        reuse_priority: 'continue_trace',
        recommended_action: 'continue_from_memory',
      },
    },
  },
};

test('AI 工作台展示任务图设计主链路与历史参考语义', async ({ page }) => {
  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        rpc_enabled: true,
      }),
    });
  });

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    const json = async (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/devices/' && method === 'GET') {
      return json([
        {
          device_id: 7,
          ip: '192.168.1.7',
          cloud_machines: [
            {
              cloud_id: 2,
              availability_state: 'available',
              machine_model_name: 'arm-box',
            },
          ],
        },
      ]);
    }
    if (path === '/api/tasks/catalog/apps' && method === 'GET') {
      return json({
        apps: [
          { id: 'default', display_name: 'Default' },
          { id: 'x', display_name: 'X' },
        ],
      });
    }
    if (path === '/api/data/accounts/parsed' && method === 'GET') {
      return json({
        accounts: [
          { account: 'demo@example.com', status: 'ready', app_id: 'default' },
          { account: 'pool-x@example.com', status: 'ready', app_id: 'x' },
        ],
      });
    }
    if (path === '/api/ai_dialog/history' && method === 'GET') {
      return json([historyItem]);
    }
    if (path === '/api/tasks/' && method === 'GET') {
      return json([]);
    }
    if (path === '/api/tasks/drafts' && method === 'GET') {
      return json([]);
    }
    if (path === '/api/tasks/metrics' && method === 'GET') {
      return json({
        rates: { failure_rate: 0.05 },
        terminal_outcomes: { completed: 4, failed: 1, cancelled: 0 },
        status_counts: { pending: 1, running: 0 },
        avg_duration_seconds: 12,
        failure_distribution: {},
      });
    }
    if (path === '/api/tasks/metrics/plugins' && method === 'GET') {
      return json([]);
    }
    if (path === '/api/tasks/drafts/draft-ai-1/snapshot' && method === 'GET') {
      return json({
        draft_id: 'draft-ai-1',
        success_threshold: 3,
        snapshot: {
          identity: {
            app_id: 'x',
            account: 'demo@example.com',
          },
          payload: {
            goal: '登录 X 并确认进入首页',
            app_id: 'x',
            account: 'demo@example.com',
            advanced_prompt: '如果出现验证码先暂停并等待人工处理',
          },
        },
      });
    }
    if (path === '/api/ai_dialog/planner' && method === 'POST') {
      return json({
        display_name: 'X 登录规划',
        operator_summary: '先判断登录状态，再执行登录，出现验证码时暂停等待人工接管。',
        account: {
          can_execute: true,
          execution_hint: '执行方式：使用已选账号 demo@example.com。',
        },
        execution: {
          runtime: 'agent_executor',
          mode: 'workflow_aligned',
          readiness: 'ready',
          blocking_reasons: [],
        },
        follow_up: {
          message: '当前无需额外补充信息。',
          missing: [],
        },
        declarative_scripts: [
          {
            name: 'x_login_decl',
            title: 'X 登录',
            role: 'login',
            description: '完成登录并确认进入首页',
          },
        ],
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'AI 工作台' }).click();
  await page.locator('#aiWorkspaceTargetSelect').selectOption('7-2');

  await expect(page.locator('#aiWorkspaceHistoryDetail')).toContainText('X 登录补链路');
  await expect(page.locator('#aiWorkspaceHistoryDetail')).toContainText('判断登录状态');
  await expect(page.locator('#aiWorkspaceHistoryDetail')).toContainText('先确认账号密码是否可用');
  await expect(page.getByRole('button', { name: '作为当前设计参考' })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续编辑草稿' })).toBeVisible();

  await page.locator('#aiWorkspaceGoal').fill('登录 X 并确认进入首页');
  await page.getByRole('button', { name: '开始设计任务图' }).click();
  await expect(page.locator('#aiWorkspacePlannerTitle')).toHaveText('X 登录规划');
  await expect(page.locator('#aiWorkspaceGraphExecution')).toContainText('运行时：agent_executor');
  await expect(page.locator('#aiWorkspaceGraphExecution')).toContainText('当前参考会话：X 登录补链路');

  await page.getByRole('button', { name: '确认任务图' }).click();
  await expect(page.locator('#aiWorkspaceGraphSummary')).toContainText('当前任务图已确认');
  await expect(page.getByRole('button', { name: '任务图已确认' })).toBeDisabled();

  await page.getByRole('button', { name: '继续编辑' }).first().click();
  await expect(page.locator('#aiWorkspaceGoal')).toHaveValue('登录 X 并确认进入首页');
  await expect(page.locator('#aiWorkspaceAdvancedPrompt')).toHaveValue('如果出现验证码先暂停并等待人工处理');
});
