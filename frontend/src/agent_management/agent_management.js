import React, { useState, useEffect } from 'react';
import {Table, Button, Modal, Form, Input, Select, message, Row, Col, Popconfirm} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { fetchGet, fetchPost } from '../utils/requestUtils';

const { TextArea } = Input;
const { Option } = Select;
const { confirm } = Modal;

const AgentManagement = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [filteredAgents, setFilteredAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [form] = Form.useForm();
  const [searchForm] = Form.useForm();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  // 添加LLM工具列表状态
  const [llmTools, setLlmTools] = useState([]);

  // 获取LLM工具列表
  const fetchLlmTools = async () => {
    fetchGet(
      '/agentApi/v1/llmTool/list?page=1&pageSize=1000',
      (data) => {
        setLlmTools(data.data.list.map(o => ({value:o.id, label:`${o.name}(${o.description})`})));
      },
      (error) => {
        messageApi.error('获取LLM工具列表失败: ' + error);
      }
    );
  };

  // 获取数据
  // 修改fetchAgents函数中的参数处理
  const fetchAgents = async (params = {}) => {
    setLoading(true);
    const { current = 1, pageSize = 20 } = pagination;
    const searchValues = searchForm.getFieldsValue();

    const queryParams = new URLSearchParams({
      page: params.page || current,
      pageSize: params.pageSize || pageSize,
      businessKey: searchValues.businessKey || '',  // 修改字段名
      name: searchValues.name || '',
      agentType: searchValues.agentType || ''  // 修改字段名
    }).toString();

    fetchGet(
        `/agentApi/v1/agentDef/list?${queryParams}`,
        (data) => {
          setFilteredAgents(data.data.list);
          setPagination({
            ...pagination,
            current: data.data.page,
            total: data.data.total,
          });
          setLoading(false);
        },
        (error) => {
          message.error('获取数据失败: ' + error);
          setLoading(false);
        }
    );
  };


  const handleTableChange = (pager) => {
    setPagination({
      ...pagination,
      current: pager.current,
      pageSize: pager.pageSize,
    });
    fetchAgents({
      page: pager.current,
      pageSize: pager.pageSize,
    });
  };

  useEffect(() => {
    fetchLlmTools(); // 获取LLM工具列表
  }, []);

  const handleSearch = (values) => {
    setPagination({
      ...pagination,
      current: 1,
    });
    fetchAgents({ page: 1 });
  };

  const handleAdd = () => {
    setEditingAgent(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record) => {
    setEditingAgent(record);
    // 设置表单字段值，包括toolIds
    form.setFieldsValue({
      ...record,
      toolIds: record.toolIds || [] // 确保toolIds是一个数组
    });
    setModalVisible(true);
  };

  const handleDelete = (id) => {
      fetchPost(
        '/agentApi/v1/agentDef/delete',
        { agentId: id },
        (data) => {
          message.success('删除成功');
          fetchAgents(); // 重新加载数据
        },
        (error) => {
          // 根据返回的错误格式显示具体错误信息
          if (error && Array.isArray(error.data) && error.data.length > 0) {
            messageApi.error(error.data[0]);
          } else {
            messageApi.error('删除失败: ' + (error.msg || error));
          }
        }
      );
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingAgent) {
        // 编辑操作
        fetchPost(
          '/agentApi/v1/agentDef/update',
          { ...values, agentId: editingAgent.id },
          (data) => {
            message.success('更新成功');
            setModalVisible(false);
            form.resetFields();
            setEditingAgent(null);
            fetchAgents(); // 重新加载数据
          },
          (error) => {
            // 根据返回的错误格式显示具体错误信息
            if (error && Array.isArray(error.data) && error.data.length > 0) {
              messageApi.error(error.data[0]);
            } else {
              messageApi.error('更新失败: ' + (error.msg || error));
            }
          }
        );
        return; // 避免执行下面的代码
      } else {
        // 新增操作
        fetchPost(
          '/agentApi/v1/agentDef/create',
          values,
          (data) => {
            message.success('添加成功');
            setModalVisible(false);
            form.resetFields();
            fetchAgents(); // 重新加载数据
          },
          (error) => {
            // 根据返回的错误格式显示具体错误信息
            if (Array.isArray(error.data) && error.data.length > 0) {
              messageApi.error(error.data[0]);
            } else {
              messageApi.error('添加失败: ' + error);
            }
          }
        );
        return; // 避免执行下面的代码
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
      dataIndex: 'businessKey',
      key: 'businessKey',
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '系统提示词',
      dataIndex: 'systemPrompt',
      key: 'systemPrompt',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'agentType',
      key: 'agentType',
      render: (text) => (text === 'dataAnalyst' ? '数据员' : '助理'),
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
          <Popconfirm
              title="请确认"
              description="请确认要删除这个Agent吗？"
              okText="是"
              cancelText="否"
              onConfirm={() => handleDelete(record.id)}
          >
            <Button danger
                    icon={<DeleteOutlined />}
                    size={"small"}
            >删除</Button>
          </Popconfirm>
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
            <Form.Item
                name="businessKey"
                label="业务键"
                rules={[{ required: true, message: '请输入业务键!' }]}
            >
              <Input placeholder="请输入业务键" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="name" label="名称">
              <Input placeholder="请输入名称" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="agentType"
                       label="类型">
              <Select placeholder="请选择类型" allowClear>
                <Option value="assistant">助理</Option>
                <Option value="dataAnalyst">数据员</Option>
              </Select>
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

                  setPagination({
                    ...pagination,
                    current: 1,
                  });
                  fetchAgents({ page: 1 });
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
        pagination={{
          ...pagination,
          showSizeChanger: true,
          pageSizeOptions: ['10', '20', '50'],
        }}
        onChange={handleTableChange}
      />

      <Modal
          title={editingAgent ? "编辑代理" : "新增代理"}
          open={modalVisible}
          onOk={handleModalOk}
          onCancel={handleModalCancel}
          okText="保存"
          cancelText="取消"
          width={600}
      >
        <Form form={form} layout="vertical">
          {contextHolder}
          <Form.Item
              name="businessKey"
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
              name="systemPrompt"
              label="系统提示词"
              rules={[{ required: true, message: '请输入系统提示词!' }]}
          >
            <TextArea rows={4} placeholder="请输入系统提示词" />
          </Form.Item>

          <Form.Item
              name="agentType"
              label="类型"
              rules={[{ required: true, message: '请选择类型!' }]}
          >
            <Select placeholder="请选择类型">
              <Option value="assistant">助理</Option>
              <Option value="dataAnalyst">数据员</Option>
            </Select>
          </Form.Item>

          <Form.Item
              name="toolIds"
              label="LLM工具"
          >
            <Select 
              mode="multiple" 
              placeholder="请选择LLM工具"
              optionFilterProp="children"
              filterOption={(input, option) => 
                option.children.toLowerCase().indexOf(input.toLowerCase()) >= 0
              }
            >
              {llmTools.map(tool => (
                <Option key={tool.value} value={tool.value}>
                  {tool.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default AgentManagement;