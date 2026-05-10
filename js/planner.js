export const templates = {
  '入门': [
    { title: '了解基本概念', weight: 0.25, tasks: ['阅读官方介绍或维基百科', '理解核心术语和定义', '记录关键概念到笔记'] },
    { title: '环境搭建与 Hello World', weight: 0.25, tasks: ['安装必要工具和依赖', '完成 Hello World 示例', '验证开发环境正常运行'] },
    { title: '核心功能实操', weight: 0.30, tasks: ['按教程完成基本功能', '理解输入输出流程', '记录遇到的问题和解决'] },
    { title: '总结与回顾', weight: 0.20, tasks: ['整理学习笔记', '列出待深入知识点', '制定下一步学习计划'] },
  ],
  '实战': [
    { title: '需求分析与设计', weight: 0.15, tasks: ['明确项目目标和范围', '设计核心功能模块', '绘制简单的系统流程图'] },
    { title: '项目脚手架搭建', weight: 0.15, tasks: ['初始化项目结构和配置', '建立开发规范和工具链', '配置持续集成/部署'] },
    { title: '核心功能开发', weight: 0.35, tasks: ['实现主要业务逻辑', '编写单元测试', '代码审查和重构'] },
    { title: '集成与联调', weight: 0.20, tasks: ['模块集成测试', '修复集成问题', '性能基准测试'] },
    { title: '部署与发布', weight: 0.15, tasks: ['编写部署文档', '部署到测试/生产环境', '监控和问题排查'] },
  ],
  '深度': [
    { title: '理论基础研究', weight: 0.15, tasks: ['阅读相关论文和白皮书', '理解底层原理和算法', '做理论笔记和思维导图'] },
    { title: '源码阅读与分析', weight: 0.20, tasks: ['clone 源码并搭建调试环境', '理解核心模块架构', '绘制关键调用链'] },
    { title: '实验验证', weight: 0.20, tasks: ['设计实验验证假设', '对比不同方案的性能/效果', '记录实验数据和结论'] },
    { title: '最佳实践提炼', weight: 0.15, tasks: ['总结常见模式和反模式', '编写最佳实践指南', '创建可复用的工具/脚本'] },
    { title: '输出与分享', weight: 0.15, tasks: ['撰写技术文章或报告', '准备演示或分享材料', '提交 PR 或改进建议'] },
    { title: '长期跟踪', weight: 0.15, tasks: ['建立知识更新机制', '关注社区动态和版本更新', '制定持续学习路线'] },
  ],
};

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
