export function inferTitleFromUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes('github.com')) {
      const [owner, repo] = u.pathname.split('/').filter(Boolean);
      if (owner && repo) return `${owner}/${repo}`;
    }
    const cleanPath = u.pathname.split('/').filter(Boolean).slice(0, 2).join(' / ');
    return cleanPath ? `${u.hostname} · ${cleanPath}` : u.hostname;
  } catch {
    return '自定义学习计划';
  }
}

export function generateLearningPlan({ url, title, category, goal, difficulty, hours }) {
  const planTitle = title?.trim() || inferTitleFromUrl(url);
  const totalMinutes = Math.max(1, Number(hours || 12)) * 60;
  const phases = [
    { name: '阶段一：背景理解与目标拆解', weight: 0.18, tasks: ['阅读项目/文章首页与 README', '整理核心概念和关键词', '明确学习目标与验收产物'] },
    { name: '阶段二：环境准备与资料梳理', weight: 0.22, tasks: ['梳理目录结构与关键章节', '准备运行/实践环境', '建立问题清单和资料索引'] },
    { name: '阶段三：核心内容精读与实践', weight: 0.4, tasks: ['逐章学习核心内容', '完成示例或实验复现', '记录关键代码/命令/知识点'] },
    { name: '阶段四：总结复盘与产出', weight: 0.2, tasks: ['补齐遗漏问题并复习', '产出学习笔记或教程', '完成总结并制定下一步'] },
  ];
  let taskIndex = 0;
  const milestones = phases.map((phase, idx) => ({
    title: phase.name,
    description: `${planTitle} · ${phase.name.replace(/^阶段.：/, '')}`,
    orderIndex: idx + 1,
    tasks: phase.tasks.map((task, i) => {
      taskIndex += 1;
      return {
        title: task,
        description: `${goal || '围绕学习链接完成结构化学习'}。来源：${url}`,
        status: 'todo',
        progress: 0,
        estimatedMinutes: Math.round((totalMinutes * phase.weight) / phase.tasks.length),
        spentMinutes: 0,
        priority: i === 0 ? 'high' : 'medium',
        orderIndex: taskIndex,
      };
    })
  }));
  return {
    title: planTitle,
    sourceUrl: url,
    description: goal || `围绕 ${planTitle} 自动生成的学习跟踪计划`,
    category: category || '未分类',
    difficulty: difficulty || '进阶',
    status: 'not_started',
    progress: 0,
    estimatedHours: Number(hours || 12),
    milestones,
  };
}
