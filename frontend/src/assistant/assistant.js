import {Content} from "antd/es/layout/layout";
import {
    Breadcrumb,
    Button, Card,
    Flex,
    Layout,
    message,
    Modal, Popover,
    Progress, Space,
    Splitter,
    Table, Tooltip,
    Tree,
    Typography,
    Upload
} from "antd";
import {Bubble, Prompts, Sender, ThoughtChain} from "@ant-design/x";
import {
    CloudUploadOutlined, FileSearchOutlined,
    LikeOutlined, LoadingOutlined, MenuOutlined, QuestionOutlined, RobotOutlined, UnorderedListOutlined,
    UploadOutlined,
    UserOutlined
} from "@ant-design/icons";
import {useEffect, useState} from "react";
import markdownit from "markdown-it";
import {useLocation} from "react-router-dom";
import { fetchGet, fetchPost, doStream } from '../utils/requestUtils';


const aiAvatar = {
    color: '#f56a00',
    backgroundColor: '#fde3cf',
};
const userAvatar = {
    color: '#fff',
    backgroundColor: '#87d068',
};

const md = markdownit({ html: true, breaks: true });

const Assistant = () => {
    const [loading, setLoading] = useState(false);
    const [bubbleLoading, setBubbleLoading] = useState(false);

    const [showCurrentAiBubble, setShowCurrentAiBubble] = useState(false);
    const [currentMsgId, setCurrentMsgId] = useState('');

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
    const [ragContent, setRagContent] = useState('');
    const [memorySize, setMemorySize] = useState(0);
    const [memoryContent, setMemoryContent] = useState("")
    const [savedMemoryContent, setSavedMemoryContent] = useState("")
    const [reasoningContent, setReasoningContent] = useState('');
    const [msgId2AddProceduralMemoryButtonAttr, setMsgId2AddProceduralMemoryButtonAttr] = useState({});
    const [msgId2FactMemoryContent, setMsgId2FactMemoryContent] = useState({});
    const [currentAddProceduralMemoryButtonAttr, setCurrentAddProceduralMemoryButtonAttr] = useState({show:false, color:"default", icon:<LikeOutlined />, canClick:true});
    const [expandedKeys, setExpandedKeys] = useState(['reasoning']);

    const [showKnowledgeRepositoryBubble, setShowKnowledgeRepositoryBubble] = useState(false);
    const [knowledgeRepositoryContent, setKnowledgeRepositoryContent] = useState('');
    const [useThinking, setUseThinking] = useState(true);
    const [promptList, setPromptList] = useState([]);



    const renderMarkdown = content => {
        return (
            <Typography>
                {/* biome-ignore lint/security/noDangerouslySetInnerHtml: used in demo */}
                <div dangerouslySetInnerHTML={{ __html: md.render(content)}} />
            </Typography>
        );
    };

    const updateAiConversationList = (content, msgId) => {
        const theList = conversationList
        theList.push({
            avatar: aiAvatar,
            placement: "start",
            content: content,
            type: 'ai',
            msgId:msgId,
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
        setShowCurrentAiBubble(true)

        fetchGet(`/agentApi/v1/assistant/welcome?businessKey=${businessKey}`, (data) => {
            setLoading( false)
            setBubbleLoading(false)
            setResponse(data.data.content)
        })
    }

    const clearAllCurrentData = () => {
        setReasoningContent( '')
        setTaskNames('')
        setTaskSize(0)
        setRagDocSize(0)
        setRagContent('')
        setMemorySize(0)
        setMemoryContent('')
        setSavedMemoryContent('')
        setCurrentMsgId('')
    }

    const submitQuestionStream = async (question) => {
        setLoading(true);
        setBubbleLoading(true)
        setShowCurrentAiBubble(true)
        setShowThoughtChain(false)
        setShowKnowledgeRepositoryBubble(false)

        clearAllCurrentData()

        // 更新AI对话
        if (response) {
            // 更新实时bubble到list
            updateAiConversationList(response, currentMsgId)

            setResponse(''); // 清空旧响应
        }

        // 更新用户对话
        if (question) {
            updateUserConversationList(question)
            setValue('')
        }

        const firstGetEvent = {current:false}
        const firstGetToken = {current:false}
        const lastMsgId = {current:''}

        const theSessionId = sessionStorage.getItem('sessionId') || sessionId;


        doStream(`/agentApi/v1/assistant/askAssistant?question=${encodeURIComponent(question)}&sessionId=${theSessionId}&businessKey=${businessKey}&useThinking=${useThinking}`,
            (event) => {
                if (event.data) {
                    if (!firstGetEvent.current) {
                        firstGetEvent.current = true
                        setShowThoughtChain(true)
                    }
                    try {
                        const data = JSON.parse(event.data);
                        if (data.token) {
                            if (!firstGetToken.current) {
                                firstGetToken.current = true
                                setBubbleLoading(false)
                            }
                            setResponse(prev => prev + data.token); // 增量更新
                        }
                        if (data.msgId && data.msgId !== '') {
                            lastMsgId.current = data.msgId
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
                        if (data.ragContent) {
                            setRagContent(data.ragContent)
                        }
                        if (data.memorySize) {
                            setMemorySize(data.memorySize)
                        }
                        if (data.memoryContent){
                            setMemoryContent(data.memoryContent)
                        }

                        // 设置生成记忆内容
                        if (data.savedMemoryContent) {
                            setSavedMemoryContent(data.savedMemoryContent)
                            setMsgId2FactMemoryContent(prevState => {
                                return {
                                    ...prevState,
                                    [lastMsgId.current]: data.savedMemoryContent
                                };
                            })
                        }

                    } catch (e) {
                        console.error('解析错误', e);
                    }
                }
            },
            () => {
                setLoading(false);
                setCurrentMsgId(lastMsgId.current)
                setCurrentAddProceduralMemoryButtonAttr(prev => ({...prev, show:true}))
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

        setUploading(true);
        setUploadProgress(0);

        try {
            // 创建一个FormData实例用于上传所有文件
            const formData = new FormData();

            // 将所有文件添加到FormData中
            fileList.forEach((fileObj, index) => {
                formData.append(`file${index}`, fileObj.originFileObj);
            });

            const response = await fetch(`/agentApi/v1/assistant/uploadMultiDocs?businessKey=${businessKey}`, {
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

    const getAddProceduralMemoryAttr = (msgId) => {
        let addProceduralMemoryButtonAttr = msgId2AddProceduralMemoryButtonAttr[msgId]
        if (!addProceduralMemoryButtonAttr) {
            return {show:true, color:"default", icon:<LikeOutlined />, canClick:true}
        } else {
            return addProceduralMemoryButtonAttr
        }
    }

    const showKnowledgeRepository= () => {
        setShowCurrentAiBubble(false)
        // 更新AI对话
        if (response) {
            // 更新实时bubble到list
            updateAiConversationList(response, currentMsgId)
            setResponse(''); // 清空旧响应
        }
        // 更新用户对话
        updateUserConversationList('浏览知识库文件')

        fetchGet(`/agentApi/v1/assistant/showKnowledgeRepository?businessKey=${businessKey}`, (data) => {
            setShowKnowledgeRepositoryBubble(true)
            setKnowledgeRepositoryContent(data.data.result)
        })
    }

    const deleteKnowledgeRepository = (fileId) => {
        fetchPost(`/agentApi/v1/assistant/deleteKnowledgeRepository`, {
            businessKey,
            fileId,
        }, (data) => {
            messageApi.success('删除成功')
            showKnowledgeRepository()
        })
    }

    const renderKnowledgeRepositoryContent =(result) => {
        let repoList = []
        for (const i in result) {
            const repo = result[i]
            repoList.push((
                <div key={i}><span>{repo[1]}<a href="#" onClick={() => deleteKnowledgeRepository(repo[0])}> 【删除】</a></span></div>
            ))
        }


        return (
            <div>
                <div><span>知识库文档如下：</span></div>
                <div style={{ height: '10px' }}></div>
                {repoList}
            </div>
        )
    }

    const addProceduralMemory = (msgId, isCurrent = false) => {
        if (isCurrent) {
            // 如果是当前对话框，需要等待对话框对话结束
            if (!currentAddProceduralMemoryButtonAttr.show) {
                messageApi.error('对话还未结束,无法生成记忆，请等待');
                return
            }
        }
        if (isCurrent) {
            setCurrentAddProceduralMemoryButtonAttr(prev => {
                return {
                    ...prev,
                    icon:<LoadingOutlined />,
                    canClick:false,
                }
            })
        } else {
            let addProceduralMemoryButtonAttr = msgId2AddProceduralMemoryButtonAttr[msgId]
            if (!addProceduralMemoryButtonAttr) {
                addProceduralMemoryButtonAttr = {}
            }
            addProceduralMemoryButtonAttr = {
                ...addProceduralMemoryButtonAttr,
                show:false,
                color:"default",
                icon:<LoadingOutlined />,
                canClick:false}
            setMsgId2AddProceduralMemoryButtonAttr(prev => {
                return {
                    ...prev,
                    msgId: addProceduralMemoryButtonAttr
                }
            })
        }


        fetchPost(`/agentApi/v1/assistant/addProceduralMemory`, {
            sessionId,
            businessKey,
            msgId
        },(data) => {
            if (data.data.success) {
                if (isCurrent) {
                    setCurrentAddProceduralMemoryButtonAttr(prev => {
                        return {
                            ...prev,
                            color: 'gold',
                            icon:<LikeOutlined />,
                            canClick:false,
                        }
                    })
                } else {
                    let addProceduralMemoryButtonAttr = msgId2AddProceduralMemoryButtonAttr[msgId]
                    addProceduralMemoryButtonAttr = {
                        ...addProceduralMemoryButtonAttr,
                        color: 'gold',
                        icon:<LikeOutlined />,
                        canClick:false,
                    }
                    setMsgId2AddProceduralMemoryButtonAttr(prev => {
                        return {
                            ...prev,
                            msgId:addProceduralMemoryButtonAttr
                        }
                    })
                }
            }
        })
    }

    const renderTitle = (icon, title) => {
        const hint = (title === '深度思考中')? '点击关闭深度思考': '点击开启深度思考'

        return (
            <Popover placement="top" title={
                <div style={{
                    textAlign: 'center',
                }}>
                    {hint}
                </div>
            } >
                <Space align="start">
                    {icon}
                    <span>{title}</span>
                </Space>
            </Popover>
        );
    }



    const openThinkingOption = ()=> {
        setPromptList(prevList => {
            const filteredList = prevList.filter(item => item.key !== 'noThinking');

            const newItem = {
                key: 'thinking',
                icon: renderTitle(<RobotOutlined style={{ color: '#FAAD14' }} />, '深度思考中'),
            };

            // 将新元素添加到列表开头
            filteredList.unshift(newItem);


            return filteredList;
        });
    }

    const closeThinkingOption = () => {
        setPromptList(prevList => {
            const filteredList = prevList.filter(item => item.key !== 'thinking');

            const newItem = {
                key: 'noThinking',
                icon: renderTitle(<MenuOutlined style={{ color: '#FAAD14' }} />, '非深度思考'),
            };

            // 将新元素添加到列表开头
            filteredList.unshift(newItem);

            return filteredList;
        });
    }

    const clickPromptItem = (item) => {
        switch (item.data.key) {
            case 'thinking':
                setUseThinking(false)
                closeThinkingOption()
                break;
            case 'noThinking':
                setUseThinking(true)
                openThinkingOption()
                break;
            case 'uploadFiles':
                showModal()
                break;
            case 'showTasks':
                setUseThinking(false)
                closeThinkingOption()
                submitQuestionStream('有哪些任务可以执行？')
                break;
            case 'fileManagement':
                showKnowledgeRepository()
                break;
            default:
                break;
        }
    }

    const getFactMemoryContent = (msgId) => {
        return msgId2FactMemoryContent[msgId]
    }

    // 初始化数据
    useEffect(() => {
        // 设置sessionId，用于做短期记忆隔离
        getSessionId()
        // 创建助手Agent
        welcome()

        setPromptList([{
            key: 'thinking',
            icon: renderTitle(<RobotOutlined style={{ color: '#FAAD14' }} />, '深度思考中'),
        },{
            key: 'showTasks',
            icon: <FileSearchOutlined style={{ color: '#FAAD14' }} />,
            description: '有哪些任务可以执行？',
        },{
            key: 'uploadFiles',
            icon: <UploadOutlined style={{ color: '#FAAD14' }} />,
            description: '上传你的知识库文档(支持多个文件，文件类型支持md,txt)',
        },{
            key: 'fileManagement',
            icon: <UnorderedListOutlined style={{ color: '#108ee9' }}  />,
            description: '浏览知识库文件',
        }]
    )
    }, []);

    const agentContentBubble = []
    for (const i in conversationList) {
        const conversation = conversationList[i]
        if (conversation.type === 'ai') {
            const buttonAttr = getAddProceduralMemoryAttr(conversation.msgId)
            const bubble = (
                <Bubble content={conversation.content} messageRender={renderMarkdown} style={{width:"55%"}}
                        avatar={{ icon: <UserOutlined />, style: conversation.avatar }} placement={conversation.placement}
                        header={"AI助理"}
                        footer={(messageContext) => (
                            <Space >
                                <Tooltip placement="bottomRight" title={getFactMemoryContent(conversation.msgId)}>
                                    <Button color={getFactMemoryContent(conversation.msgId) ? "gold":"default"} variant="text" size="small" icon={<CloudUploadOutlined  />} disabled={true}/>
                                </Tooltip>
                                <Button color={buttonAttr.color} variant="text" size="small" icon={buttonAttr.icon} onClick={buttonAttr.canClick ? () => addProceduralMemory(conversation.msgId): () => {}} />
                            </Space>
                        )}
                />
            )
            agentContentBubble.push(bubble)
        } else {
            const bubble = (
                <Bubble content={conversation.content} style={{width:"55%",marginLeft: 'auto'}}
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

    const thoughtChainItems = [
        {
            key: 'tasks',
            title: `已有${taskSize}个数据查询任务`,
            content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{`已有数据查询任务:${taskNames}`}</div>,
            status: 'success',
        },
        {
            key: 'ragDocs',
            title: `检索到${ragDocSize}个文档`,
            content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{ragContent}</div>,
            status: 'success',
        },
        {
            key: 'memories',
            title: `检索到${memorySize}个相关记忆`,
            content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{memoryContent}</div>,
            status: 'success',
        }
    ]
    if (useThinking) {
        thoughtChainItems.push(
            {
                key: 'reasoning',
                title: '深度思考',
                content: <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{reasoningContent}</div>,
                status: 'success',
            })
    }

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
                        <ThoughtChain items={thoughtChainItems} collapsible={collapsible} />
                    </Card>
                    <Bubble loading={bubbleLoading} content={response} messageRender={renderMarkdown} style={showCurrentAiBubble?{width:"55%"}:{visibility: 'hidden'}}
                            avatar={{ icon: <UserOutlined />, style: aiAvatar }} placement={"start"}
                            header={"AI数据员"}
                            footer={(messageContext) => (
                                <Space >
                                    <Tooltip placement="bottomRight" title={savedMemoryContent}>
                                        <Button color={savedMemoryContent === "" ? "default":"gold"} variant="text" size="small" icon={<CloudUploadOutlined  />} disabled={true}/>
                                    </Tooltip>
                                    <Button disabled={loading} color={currentAddProceduralMemoryButtonAttr.color} variant="text" size="small" icon={currentAddProceduralMemoryButtonAttr.icon} onClick={currentAddProceduralMemoryButtonAttr.canClick ? () => addProceduralMemory(currentMsgId, true) : () => {}} />
                                </Space>
                            )}
                    />
                    <Bubble content={knowledgeRepositoryContent} messageRender={renderKnowledgeRepositoryContent} style={showKnowledgeRepositoryBubble?{width:"55%"}:{visibility: 'hidden'}}
                            avatar={{ icon: <UserOutlined />, style: aiAvatar }} placement={"start"}
                            header={"AI数据员"}
                    />
                    {contextHolder}

                    <Prompts title="常用操作：" items={promptList}
                             onItemClick={clickPromptItem}/>
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
                    accept=".md,.txt"
                    maxCount={10}
                    multiple={true}
                >
                    <Button icon={<UploadOutlined />}>选择文件</Button>
                </Upload>

                {fileList.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                        <p>已选择 {fileList.length} 个文件:</p>
                        <ul>
                            {fileList.map((file, index) => (
                                <li key={index}>{file.name}</li>
                            ))}
                        </ul>
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