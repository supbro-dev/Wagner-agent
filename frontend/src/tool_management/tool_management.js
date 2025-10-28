import React from 'react';
import { Tabs } from 'antd';
import AgentManagement from '../agent_management/agent_management';
import LLMToolManagement from '../llm_tool_management/llm_tool_management';

const ToolManagement = () => {
  return (
    <div style={{ padding: '24px' }}>
      <Tabs defaultActiveKey="1" type="card">
        <Tabs.TabPane tab="Agent管理" key="1">
          <AgentManagement />
        </Tabs.TabPane>
        <Tabs.TabPane tab="工具管理" key="2">
          <LLMToolManagement />
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default ToolManagement;