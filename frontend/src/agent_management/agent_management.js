import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Row, Col } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;

const AgentManagement = () => {
  const [agents, setAgents] = useState([]);
  const [filteredAgents, setFilteredAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [form] = Form.useForm();
  const [searchForm] = Form.useForm();

  // 模拟获取数据
  const fetchAgents = async () => {
    setLoading(true);
    try {
      // 这里应该调用实际的API接口
      // const response = await fetch('/api/agents');
      // const data = await response.json();
      
      // 模拟数据
      const mockData = [
        {
          id: 1,
          business_key: 'data_analyst_001',
          name: '数据分析员1号',
          system_prompt: '你是一个专业的数据分析师...',
          agent_type: '数据员'
        },
        {
          id: 2,
          business_key: 'assistant_001',
          name: '智能助理1号',
          system_prompt: '你是一个智能助理...',
          agent_type: '助理'
        }
      ];
      setAgents(mockData);
      setFilteredAgents(mockData);
    } catch (error) {
      message.error('获取数据失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleSearch = (values) => {
    const { name, agent_type, business_key } = values;
    let result = agents;

    if (name) {
      result = result.filter(agent => agent.name.includes(name));
    }

    if (agent_type) {
      result = result.filter(agent => agent.agent_type === agent_type);
    }

    if (business_key) {
      result = result.filter(agent => agent.business_key.includes(business_key));
    }

    setFilteredAgents(result);
  };

  const handleAdd = () => {
    setEditingAgent(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record) => {
    setEditingAgent(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleDelete = (id) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个代理吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          // 这里应该调用实际的API接口
          // await fetch(`/api/agents/${id}`, { method: 'DELETE' });
          
          message.success('删除成功');
          fetchAgents(); // 重新加载数据
        } catch (error) {
          message.error('删除失败: ' + error.message);
        }
      }
    });
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingAgent) {
        // 编辑操作
        // await fetch(`/api/agents/${editingAgent.id}`, {
        //   method: 'PUT',
        //   headers: { 'Content-Type': 'application/json' },
        //   body: JSON.stringify(values)
        // });
        message.success('更新成功');
      } else {
        // 新增操作
        // await fetch('/api/agents', {
        //   method: 'POST',
        //   headers: { 'Content-Type': 'application/json' },
        //   body: JSON.stringify(values)
        // });
        message.success('添加成功');
      }
      
      setModalVisible(false);
      form.resetFields();
      fetchAgents(); // 重新加载数据
    } catch (error) {
      message.error('操作失败: ' + error.message);
    }
  };

  const handleModalCancel = () => {
    setModalVisible(false);
    form.resetFields();
    setEditingAgent(null);
  };

  const columns = [
    {
      title: '业务键',
      dataIndex: 'business_key',
      key: 'business_key',
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '系统提示词',
      dataIndex: 'system_prompt',
      key: 'system_prompt',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'agent_type',
      key: 'agent_type',
      render: (text) => (text === '数据员' ? '数据员' : '助理'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <span>
          <Button 
            type="primary" 
            icon={<EditOutlined />} 
            onClick={() => handleEdit(record)}
            style={{ marginRight: 8 }}
            size="small"
          >
            编辑
          </Button>
          <Button 
            danger 
            icon={<DeleteOutlined />} 
            onClick={() => handleDelete(record.id)}
            size="small"
          >
            删除
          </Button>
        </span>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      {/* 搜索表单 */}
      <Form form={searchForm} onFinish={handleSearch} layout="inline" style={{ marginBottom: 16 }}>
        <Row gutter={16} style={{ width: '100%' }}>
          <Col span={6}>
            <Form.Item name="name" label="名称">
              <Input placeholder="请输入名称" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="agent_type" label="类型">
              <Select placeholder="请选择类型" allowClear>
                <Option value="数据员">数据员</Option>
                <Option value="助理">助理</Option>
              </Select>
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="business_key" label="业务键">
              <Input placeholder="请输入业务键" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item>
              <Button type="primary" htmlType="submit" style={{ marginRight: 8 }}>
                查询
              </Button>
              <Button 
                onClick={() => {
                  searchForm.resetFields();
                  setFilteredAgents(agents);
                }}
              >
                重置
              </Button>
            </Form.Item>
          </Col>
        </Row>
      </Form>
      
      <div style={{ marginBottom: 16 }}>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={handleAdd}
        >
          新增Agent
        </Button>
      </div>
      
      <Table
        dataSource={filteredAgents}
        columns={columns}
        loading={loading}
        rowKey="id"
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingAgent ? "编辑代理" : "新增代理"}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="business_key"
            label="业务键"
            rules={[{ required: true, message: '请输入业务键!' }]}
          >
            <Input placeholder="请输入业务键" />
          </Form.Item>
          
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称!' }]}
          >
            <Input placeholder="请输入名称" />
          </Form.Item>
          
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true, message: '请输入系统提示词!' }]}
          >
            <TextArea rows={4} placeholder="请输入系统提示词" />
          </Form.Item>
          
          <Form.Item
            name="agent_type"
            label="类型"
            rules={[{ required: true, message: '请选择类型!' }]}
          >
            <Select placeholder="请选择类型">
              <Option value="数据员">数据员</Option>
              <Option value="助理">助理</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AgentManagement;