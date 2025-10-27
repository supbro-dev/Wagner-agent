create table if not exists agent_def
(
    id            bigint auto_increment comment 'id'
        primary key,
    gmt_create    datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    gmt_modified  datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '修改时间',
    business_key  varchar(256)                       not null comment '业务键',
    name          varchar(256)                       not null comment '名称',
    system_prompt text                               not null comment '系统提示词',
    agent_type    varchar(32)                        not null comment 'agent类型(数据员/助理)'
)
    comment 'agent定义';

create index idx_bk
    on agent_def (business_key);

create table if not exists agent_llm_tool
(
    id           bigint auto_increment comment 'id'
        primary key,
    gmt_create   datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    gmt_modified datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '修改时间',
    agent_id     bigint                             not null comment 'agentId',
    llm_tool_id  bigint                             not null comment 'llm工具id'
)
    comment 'agent与llm_tool关联关系';

create index idx_ai
    on agent_llm_tool (agent_id);

create table if not exists llm_tool
(
    id                     bigint auto_increment comment 'id'
        primary key,
    gmt_create             datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    gmt_modified           datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '修改时间',
    name                   varchar(128)                       not null comment '工具名称',
    description            text                               not null comment '工具描述信息',
    args_dict              json                               not null comment '参数名及描述(参数名->描述信息)',
    tool_type              varchar(16)                        not null comment '工具类型(http/mcp)',
    content                json                               not null comment '工具内容',
    request_handle_script  text                               null comment '请求处理脚本',
    response_handle_script text                               null comment '响应处理脚本'
)
    comment '大模型工具';

create table if not exists query_data_task
(
    id           bigint auto_increment comment 'id'
        primary key,
    gmt_create   datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    gmt_modified datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '修改时间',
    business_key varchar(64)                        not null comment '业务域',
    name         varchar(128)                       not null comment '任务名称',
    task_detail  json                               not null comment '任务信息',
    invoke_times int      default 0                 not null comment '执行次数',
    is_deleted   tinyint  default 0                 not null comment '是否删除',
    execute_time datetime                           null comment '最近执行时间',
    constraint uk_bk_name
        unique (business_key, name)
)
    comment '数据查询任务';

create table if not exists rag_file
(
    id           bigint auto_increment comment 'id'
        primary key,
    gmt_create   datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    gmt_modified datetime default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment '更新时间',
    file_name    varchar(128)                       not null comment '文件名称',
    content      text                               not null comment '内容',
    business_key varchar(128)                       not null comment '业务键'
)
    comment '简易rag文件记录';

create index idx_bk_fn
    on rag_file (business_key, file_name);

