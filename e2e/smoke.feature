Feature: Learning Tracker 冒烟测试 — Smoke Tests

  # ============================================================
  # 场景 1: 登录页加载验证
  # ============================================================
  Scenario: 登录页面正常加载并显示标题
    Given a user is on the URL as ${E2E_BASE_URL}
    Then the user should see "Learning Tracker" text on the page
    And the user should see "MySQL 多用户学习计划跟踪系统" text on the page

  # ============================================================
  # 场景 2: 错误密码登录失败
  # ============================================================
  Scenario: 使用错误密码登录应失败
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "wrongpassword" into the password field
    And the user clicks the "登录" button
    Then the user should see an error message on the page

  # ============================================================
  # 场景 3: 正确凭据登录成功并进入仪表盘
  # ============================================================
  Scenario: 使用正确凭据登录成功进入仪表盘
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page

  # ============================================================
  # 场景 4: 仪表盘导航到学习计划视图
  # ============================================================
  Scenario: 从仪表盘导航到学习计划视图
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page
    When the user clicks the "学习计划" navigation button
    Then the user should see "学习计划" text on the page

  # ============================================================
  # 场景 5: 导航到学习日志视图
  # ============================================================
  Scenario: 导航到学习日志视图
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page
    When the user clicks the "学习日志" navigation button
    Then the user should see "学习日志" text on the page

  # ============================================================
  # 场景 6: 导航到数据管理视图
  # ============================================================
  Scenario: 导航到数据管理视图
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page
    When the user clicks the "数据管理" navigation button
    Then the user should see "数据管理" text on the page

  # ============================================================
  # 场景 7: 管理员导航到 AI 模型配置视图
  # ============================================================
  Scenario: 管理员导航到 AI 模型配置视图
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page
    When the user clicks the "AI 模型配置" navigation button
    Then the user should see "AI 模型配置" text on the page

  # ============================================================
  # 场景 8: 退出登录返回登录页
  # ============================================================
  Scenario: 退出登录返回登录页面
    Given a user is on the URL as ${E2E_BASE_URL}
    When the user enters "admin@cpaas.io" into the username field
    And the user enters "K8sMysql2024!" into the password field
    And the user clicks the "登录" button
    Then the user should see "仪表盘" text on the page
    When the user clicks the "退出登录" button
    Then the user should see "Learning Tracker" text on the page