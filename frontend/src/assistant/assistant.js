import {Content} from "antd/es/layout/layout";
import {
    Breadcrumb,
    Button, Card,
    Flex,
    Layout,
    message,
    Modal,
    Progress,
    Splitter,
    Table,
    Tree,
    Typography,
    Upload
} from "antd";
import {Bubble, Prompts, Sender, ThoughtChain} from "@ant-design/x";
import {MoreOutlined, RocketOutlined, UploadOutlined, UserOutlined} from "@ant-design/icons";
import {useEffect, useState} from "react";
import markdownit from "markdown-it";
import {useLocation} from "react-router-dom";
import { fetchGet, fetchPost, doStream } from '../utils/requestUtils';
import {Line} from "@ant-design/plots";
const { Paragraph, Text } = Typography;

const aiAvatar = {
    color: '#f56a00',
    backgroundColor: '#fde3cf',
};
const userAvatar = {
    color: '#fff',
    backgroundColor: '#87d068',
};

const md = markdownit({ html: true, breaks: true });

const promptList = [{
    key: '0',
    icon: <UploadOutlined style={{ color: '#FAAD14' }} />,
    description: '上传你的知识库文档(支持markdown)',
    disabled: false,
}]




const items = [
    {
        key: 'item-1',
        title: 'Click me to expand the content',
        content: "dkdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        status: 'success',
    }
];

const Assistant = () => {
    const [loading, setLoading] = useState(false);
    const [bubbleLoading, setBubbleLoading] = useState(false);
    const [showNewAiBubble, setShowNewAiBubble] = useState(false);
    const [value, setValue] = useState('');
    const [response, setResponse] = useState('');
    const [messageApi, contextHolder] = message.useMessage();
    const [sessionId, setSessionId] = useState('');

    // 添加文件上传相关状态
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [fileList, setFileList] = useState([]);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploading, setUploading] = useState(false);

    // 对话相关
    const [conversationList, setConversationList] = useState([]);


    const location = useLocation();
    // 使用 URLSearchParams 解析查询字符串
    const queryParams = new URLSearchParams(location.search);
    const businessKey = queryParams.get('businessKey');

    const [showThoughtChain, setShowThoughtChain] = useState(false);
    const [taskSize, setTaskSize] = useState(0)
    const [taskNames, setTaskNames] = useState('');
    const [ragDocSize, setRagDocSize] = useState(0)
    const [ragDocNameList, setRagDocNameList] = useState([]);
    const [memorySize, setMemorySize] = useState(0);
    const [memoryContent, setMemoryContent] = useState("")
    const [reasoningContent, setReasoningContent] = useState('');
    const [expandedKeys, setExpandedKeys] = useState(['reasoning']);



    const renderMarkdown = content => {
        return (
            <Typography>
                {/* biome-ignore lint/security/noDangerouslySetInnerHtml: used in demo */}
                <div dangerouslySetInnerHTML={{ __html: md.render(content)}} />
            </Typography>
        );
    };

    const updateAiConversationList = (content) => {
        const theList = conversationList
        theList.push({
            avatar: aiAvatar,
            placement: "start",
            content: content,
            type: 'ai',
        })
        setConversationList(theList)
    }

    const updateUserConversationList = (content) => {
        const theList = conversationList
        theList.push({
            avatar:userAvatar,
            placement:"end",
            content:content,
            type:'human',
        })
        setConversationList(theList)
    }

    const getSessionId = () => {
        // 生成或获取 sessionId
        let sessionId = sessionStorage.getItem('sessionId');

        if (!sessionId) {
            // 生成唯一 ID（使用时间戳和随机数）
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('sessionId', sessionId);
        }

        setSessionId(sessionId);
    }

    const welcome = async () => {
        setLoading(true);
        setBubbleLoading(true)
        setShowNewAiBubble(true)

        fetchGet(`/agentApi/v1/assistant/welcome?businessKey=${businessKey}`, (data) => {
            setLoading( false)
            setBubbleLoading(false)
            setResponse(data.data.content)
        })
    }

    const submitQuestionStream = async (question) => {
        setLoading(true);
        setBubbleLoading(true)
        setShowNewAiBubble(true)
        setShowThoughtChain(false)

        // 更新AI对话
        if (response) {
            // 更新实时bubble到list
            updateAiConversationList(response)

            setResponse(''); // 清空旧响应
        }

        // 更新用户对话
        if (question) {
            updateUserConversationList(question)
            setValue('')
        }

        const firstGetEvent = {current:false}

        doStream(`/agentApi/v1/assistant/askAssistant?question=${encodeURIComponent(question)}&sessionId=${sessionId}&businessKey=${businessKey}`,
            (event) => {
                if (event.data) {
                    if (!firstGetEvent.current) {
                        firstGetEvent.current = true
                        setBubbleLoading(false)
                        setShowThoughtChain(true)
                    }
                    try {
                        const data = JSON.parse(event.data);
                        if (data.token) {
                            setResponse(prev => prev + data.token); // 增量更新
                        }
                        // 设置推理内容
                        if (data.reasoningContent) {
                            setReasoningContent(prev => prev + data.reasoningContent) // 增量更新
                        }
                        // 设置查询任务总数
                        if (data.taskSize) {
                            setTaskSize(data.taskSize)
                            setTaskNames(data.taskNames)
                        }
                        // 设置检索到的文档数
                        if (data.ragDocSize) {
                            setRagDocSize(data.ragDocSize)
                        }
                        // 设置检索到的文档名称
                        if (data.ragDocNameList) {
                            setRagDocNameList(data.ragDocNameList)
                        }

                    } catch (e) {
                        console.error('解析错误', e);
                    }
                }
            },
            () => {
                setLoading(false);
            },
            () => {
                setLoading(false);
            }
        )
    };

    // 显示上传模态框
    const showModal = () => {
        setIsModalVisible(true);
    };

    // 隐藏上传模态框
    const handleCancel = () => {
        setIsModalVisible(false);
        setFileList([]);
        setUploadProgress(0);
    };

    // 文件上传处理函数
    const handleFileUpload = async () => {
        if (fileList.length === 0) return;

        const file = fileList[0].originFileObj;
        const formData = new FormData();
        formData.append('file', file);

        setUploading(true);
        setUploadProgress(0);

        try {
            const response = await fetch(`/agentApi/v1/assistant/uploadFile?businessKey=${businessKey}`, {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const result = await response.json();
                messageApi.success('文件上传成功');
                // 重置状态
                setFileList([]);
                setUploadProgress(100);
                // 延迟关闭模态框
                setTimeout(() => {
                    setIsModalVisible(false);
                    setUploading(false);
                }, 1000);
                return result;
            } else {
                messageApi.error('文件上传失败');
                setUploading(false);
            }
        } catch (error) {
            messageApi.error('上传过程中发生错误');
            console.error('Upload error:', error);
            setUploading(false);
        }
    };


    // 处理文件选择变化
    const handleFileChange = ({ fileList: newFileList }) => {
        setFileList(newFileList);
    };

    // 初始化数据
    useEffect(() => {
        // 设置sessionId，用于做短期记忆隔离
        getSessionId()
        // 创建助手Agent
        welcome()
    }, []);

    const agentContentBubble = []
    for (const i in conversationList) {
        const conversation = conversationList[i]
        if (conversation.type === 'ai') {
            const bubble = (
                <Bubble content={conversation.content} messageRender={renderMarkdown}
                        avatar={{ icon: <UserOutlined />, style: conversation.avatar }} placement={conversation.placement}
                        header={"AI助理"}
                />
            )
            agentContentBubble.push(bubble)
        } else {
            const bubble = (
                <Bubble content={conversation.content}
                        avatar={{ icon: <UserOutlined />, style: conversation.avatar }} placement={conversation.placement} />
            )

            agentContentBubble.push(bubble)
        }
    }


    const collapsible = {
        expandedKeys,
        onExpand: keys => {
            setExpandedKeys(keys);
        },
    };

    return (
        <Layout >
            <Content style={{ padding: '0 48px' }}>
                {/* 面包屑导航 */}
                <Breadcrumb>
                    <Breadcrumb.Item>
                        <span>首页</span>
                    </Breadcrumb.Item>
                    <Breadcrumb.Item>
                        <span>数据分析</span>
                    </Breadcrumb.Item>
                    <Breadcrumb.Item>
                        <strong>AI助理</strong>
                    </Breadcrumb.Item>
                </Breadcrumb>
                <Flex vertical gap="middle">
                    {agentContentBubble}
                    <Card style={{ width: '55%' }} hidden={!showThoughtChain}>
                        <ThoughtChain items={ [
                            {
                                key: 'tasks',
                                title: `已有${taskSize}个数据查询任务`,
                                content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{`已有数据查询任务:${taskNames}`}</div>,
                                status: 'success',
                            },
                            {
                                key: 'ragDocs',
                                title: `检索到${ragDocSize}个文档`,
                                content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{ragDocNameList}</div>,
                                status: 'success',
                            },
                            {
                                key: 'memories',
                                title: `检索到${memorySize}个相关记忆`,
                                content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{memoryContent}</div>,
                                status: 'success',
                            },
                            {
                                key: 'reasoning',
                                title: '深度思考',
                                content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{reasoningContent}</div>,
                                status: 'success',
                            }
                        ]} collapsible={collapsible} />
                    </Card>
                    <Bubble loading={bubbleLoading} content={response} messageRender={renderMarkdown} style={showNewAiBubble?{}:{visibility: 'hidden'}}
                            avatar={{ icon: <UserOutlined />, style: aiAvatar }} placement={"start"}
                            header={"AI数据员"}
                    />

                    {contextHolder}
                    <Prompts title="" items={promptList} onItemClick={info => {
                        showModal();
                    }}/>
                    <Sender
                        loading={loading}
                        value={value}
                        onChange={(v) => {
                            setValue(v);
                        }}
                        onSubmit={submitQuestionStream}
                        onCancel={() => {
                            setLoading(false);
                        }}
                        autoSize={{ minRows: 2, maxRows: 6 }}
                    />
                </Flex>
            </Content>
            <Modal
                title="上传知识库文档"
                open={isModalVisible}
                onCancel={handleCancel}
                footer={[
                    <Button key="cancel" onClick={handleCancel}>
                        取消
                    </Button>,
                    <Button
                        key="upload"
                        type="primary"
                        onClick={handleFileUpload}
                        disabled={fileList.length === 0 || uploading}
                        loading={uploading}
                    >
                        {uploading ? '上传中...' : '开始上传'}
                    </Button>
                ]}
            >
                <Upload
                    fileList={fileList}
                    onChange={handleFileChange}
                    beforeUpload={() => false} // 阻止默认上传行为
                    accept=".md,.markdown"
                    maxCount={1}
                >
                    <Button icon={<UploadOutlined />}>选择文件</Button>
                </Upload>

                {fileList.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                        <p>已选择文件: {fileList[0].name}</p>
                        {uploading && (
                            <Progress percent={uploadProgress} status="active" />
                        )}
                    </div>
                )}
            </Modal>

        </Layout>
    )
}

export default Assistant;