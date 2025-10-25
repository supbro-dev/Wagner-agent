// utils/requestUtils.js

/**
 * 通用的GET请求方法
 * @param {string} url - 请求URL
 * @param {Function} successHandler - 成功回调函数
 * @param {Function} errorHandler - 错误处理函数（可选）
 */
export const fetchGet = (url, successHandler, errorHandler) => {
    try {
        fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        })
            .then(response => response.json())
            .then(data => {
                if (data.code !== 0) {
                    if (errorHandler) {
                        errorHandler(data.msg);
                    } else {
                        console.error('请求失败:', data.msg);
                    }
                } else {
                    if (successHandler) {
                        successHandler(data);
                    }
                }
            })
            .catch((err) => {
                if (errorHandler) {
                    errorHandler(err.message);
                } else {
                    console.error('Error:', err);
                }
            });
    } catch (error) {
        if (errorHandler) {
            errorHandler(error.message);
        } else {
            console.error('请求异常:', error);
        }
    }
};

/**
 * 通用的POST请求方法
 * @param {string} url - 请求URL
 * @param {Object} data - 请求体数据
 * @param {Function} successHandler - 成功回调函数
 * @param {Function} errorHandler - 错误处理函数（可选）
 */
export const fetchPost = (url, data, successHandler, errorHandler) => {
    try {
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        })
            .then(response => response.json())
            .then(data => {
                if (data.code !== 0) {
                    if (errorHandler) {
                        errorHandler(data);
                    } else {
                        console.error('请求失败:', data.msg);
                    }
                } else {
                    if (successHandler) {
                        successHandler(data);
                    }
                }
            })
            .catch((err) => {
                if (errorHandler) {
                    errorHandler(err);
                } else {
                    console.error('Error:', err);
                }
            });
    } catch (error) {
        if (errorHandler) {
            errorHandler(error);
        } else {
            console.error('请求异常:', error);
        }
    }
};

/**
 * SSE流式请求方法
 * @param {string} url - 请求URL
 * @param {Function} onmessageHandler - 消息处理函数
 * @param {Function} finishHandler - 完成回调函数
 * @param {Function} errorHandler - 错误处理函数
 */
export const doStream = (url, onmessageHandler, finishHandler, errorHandler) => {
    // 建立SSE连接
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
        // 注意：SSE的默认事件类型是'message'，数据在event.data中
        if (event.data) {
            if (onmessageHandler) {
                onmessageHandler(event);
            }
        }
    };

    // 监听自定义的'done'事件
    eventSource.addEventListener('done', () => {
        eventSource.close();
        if (finishHandler) {
            finishHandler();
        }
    });

    eventSource.onerror = (err) => {
        eventSource.close();
        if (errorHandler) {
            errorHandler(err);
        }
    };

    // 返回eventSource实例，以便外部可以手动关闭连接
    return eventSource;
};
