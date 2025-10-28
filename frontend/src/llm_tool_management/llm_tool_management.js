import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Row, Col, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { fetchGet, fetchPost } from '../utils/requestUtils';

const { TextArea } = Input;
const { Option } = Select;

const LLMToolManagement = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingTool, setEditingTool] = useState(null);
  const [form] = Form.useForm();
  const [searchForm] = Form.useForm();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  // 获取数据
  const fetchTools = async (params = {}) => {
    setLoading(true);
    const { current = 1, pageSize = 20 } = pagination;
    const searchValues = searchForm.getFieldsValue();

    const queryParams = new URLSearchParams({
      page: params.page || current,
      pageSize: params.pageSize || pageSize,
      name: searchValues.name || '',
      toolType: searchValues.toolType || ''
    }).toString();

    fetchGet(
      `/agentApi/v1/llmTool/list?${queryParams}`,
      (data) => {
        setTools(data.data.list);
        setPagination({
          ...pagination,
          current: data.data.page,
          total: data.data.total,
        });
        setLoading(false);
      },
      (error) => {
        messageApi.error('获取数据失败: ' + error);
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
    fetchTools({
      page: pager.current,
      pageSize: pager.pageSize,
    });
  };

  useEffect(() => {
    // 初始化数据
    fetchTools();
  }, []);

  const handleSearch = (values) => {
    setPagination({
      ...pagination,
      current: 1,
    });
    fetchTools({ page: 1 });
  };

  const handleAdd = () => {
    setEditingTool(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (record) => {
    setEditingTool(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleDelete = (id) => {
    fetchPost(
      '/agentApi/v1/llmTool/delete',
      { toolId: id },
      (data) => {
        messageApi.success('删除成功');
        fetchTools(); // 重新加载数据
      },
      (error) => {
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
      
      // 根据工具类型过滤不需要提交的字段
      let submitValues = { ...values };
      if (values.toolType === 'mcp') {
        // 如果是MCP类型，移除不需要的字段
        delete submitValues.argsDict;
        delete submitValues.requestHandleScript;
        delete submitValues.responseHandleScript;
      }

      if (editingTool) {
        // 编辑操作
        fetchPost(
          '/agentApi/v1/llmTool/update',
          { ...submitValues, toolId: editingTool.id },
          (data) => {
            if (values.toolType === "mcp") {
              messageApi.success("MCP SERVER包含以下工具:" + data.data.result);
            } else {
              messageApi.success(data.data.result);
            }
            setModalVisible(false);
            form.resetFields();
            setEditingTool(null);
            fetchTools(); // 重新加载数据
          },
          (error) => {
            if (error && Array.isArray(error.data) && error.data.length > 0) {
              messageApi.error(error.data[0]);
            } else {
              messageApi.error('更新失败: ' + (error.msg || error));
            }
          }
        );
      } else {
        // 新增操作
        fetchPost(
          '/agentApi/v1/llmTool/create',
          submitValues,
          (data) => {
            if (values.toolType === "mcp") {
              messageApi.success("MCP SERVER包含以下工具:" + data.data.result);
            } else {
              messageApi.success(data.data.result);
            }
            setModalVisible(false);
            form.resetFields();
            fetchTools(); // 重新加载数据
          },
          (error) => {
            if (Array.isArray(error.data) && error.data.length > 0) {
              messageApi.error(error.data[0]);
            } else {
              messageApi.error('添加失败: ' + error);
            }
          }
        );
      }
    } catch (error) {
      messageApi.error('操作失败: ' + error.message);
    }
  };

  const handleModalCancel = () => {
    setModalVisible(false);
    form.resetFields();
    setEditingTool(null);
  };

  const handleTestRun = async () => {
    try {
      const values = await form.validateFields();
      
      // 根据工具类型过滤不需要提交的字段
      let submitValues = { ...values };
      if (values.toolType === 'mcp') {
        // 如果是MCP类型，移除不需要的字段
        delete submitValues.argsDict;
        delete submitValues.requestHandleScript;
        delete submitValues.responseHandleScript;
      }

      // 执行试运行
      fetchPost(
        '/agentApi/v1/llmTool/testRun',
        submitValues,
        (data) => {
          if (values.toolType === "mcp") {
            messageApi.success("MCP SERVER包含以下工具:" + data.data.result);
          } else {
            messageApi.success("试运行成功: " + data.data.result);
          }
        },
        (error) => {
          if (Array.isArray(error.data) && error.data.length > 0) {
            messageApi.error(error.data[0]);
          } else {
            messageApi.error('试运行失败: ' + error);
          }
        }
      );
    } catch (error) {
      messageApi.error('操作失败: ' + error.message);
    }
  };

  const columns = [
    {
      title: '工具名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '工具描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '工具类型',
      dataIndex: 'toolType',
      key: 'toolType',
      render: (text) => (text === 'httpTool' ? 'HTTP工具' : 'MCP'),
    },
    {
      title: '创建时间',
      dataIndex: 'gmtCreate',
      key: 'gmtCreate',
    },
    {
      title: '修改时间',
      dataIndex: 'gmtModified',
      key: 'gmtModified',
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
            description="请确认要删除这个工具吗？"
            okText="是"
            cancelText="否"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button 
              danger
              icon={<DeleteOutlined />}
              size="small"
            >
              删除
            </Button>
          </Popconfirm>
        </span>
      ),
    },
  ];

  // 获取当前表单中的工具类型值
  const toolTypeValue = Form.useWatch('toolType', form);

  return (
    <div style={{ padding: '24px' }}>
      {/* 搜索表单 */}
      <Form form={searchForm} onFinish={handleSearch} layout="inline" style={{ marginBottom: 16 }}>
        <Row gutter={16} style={{ width: '100%' }}>
          <Col span={6}>
            <Form.Item name="name" label="工具名称">
              <Input placeholder="请输入工具名称" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="toolType" label="工具类型">
              <Select placeholder="请选择工具类型" allowClear>
                <Option value="httpTool">HTTP工具</Option>
                <Option value="mcp">MCP</Option>
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
                  fetchTools({ page: 1 });
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
          新增工具
        </Button>
      </div>

      <Table
        dataSource={tools}
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
        title={editingTool ? "编辑工具" : "新增工具"}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        okText="保存"
        cancelText="取消"
        width={600}
        footer={[
          <Button key="testRun" type="primary" onClick={handleTestRun}>
            试运行
          </Button>,
          <Button key="cancel" onClick={handleModalCancel}>
            取消
          </Button>,
          <Button key="ok" type="primary" onClick={handleModalOk}>
            保存
          </Button>,
        ]}
      >
        <Form form={form} layout="vertical">
          {contextHolder}
          <Form.Item
            name="name"
            label="工具名称"
            rules={[{ required: true, message: '请输入工具名称!' }]}
          >
            <Input placeholder="请输入工具名称" />
          </Form.Item>

          <Form.Item
            name="description"
            label="工具描述"
            rules={[{ required: true, message: '请输入工具描述!' }]}
          >
            <TextArea rows={4} placeholder="请输入工具描述" />
          </Form.Item>

          <Form.Item
            name="toolType"
            label="工具类型"
            rules={[{ required: true, message: '请选择工具类型!' }]}
          >
            <Select placeholder="请选择工具类型">
              <Option value="httpTool">HTTP工具</Option>
              <Option value="mcp">MCP</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="content"
            label="工具内容"
            rules={[{ required: true, message: '请输入工具内容!' }]}
          >
            <TextArea rows={4} placeholder="请输入工具内容" />
          </Form.Item>

          {/* 当工具类型不是MCP时显示以下字段 */}
          {toolTypeValue !== 'mcp' && (
            <>
              <Form.Item
                name="argsDict"
                label="参数字典"
                rules={[{ required: true, message: '请输入参数字典!' }]}
              >
                <TextArea rows={4} placeholder="请输入参数字典" />
              </Form.Item>

              <Form.Item
                name="requestHandleScript"
                label="请求处理脚本"
              >
                <TextArea rows={4} placeholder="请输入请求处理脚本（可选）" />
              </Form.Item>

              <Form.Item
                name="responseHandleScript"
                label="响应处理脚本"
              >
                <TextArea rows={4} placeholder="请输入响应处理脚本（可选）" />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default LLMToolManagement;