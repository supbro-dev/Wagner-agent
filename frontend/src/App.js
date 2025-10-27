import React from 'react';

import DataClerk from "./data_clerk/data_clerk";
import Assistant from "./assistant/assistant";
import AgentManagement from "./agent_management/agent_management";
import LLMToolManagement from "./llm_tool_management/llm_tool_management";
import './App.css';
import {BrowserRouter, Route, Routes} from "react-router-dom";

function App() {
    return (
        <BrowserRouter basename="/web">
            <Routes>
                <Route path="/dataClerk" element={<DataClerk />} />
                <Route path="/assistant" element={<Assistant />} />
                <Route path="/agentManagement" element={<AgentManagement />} />
                <Route path="/llmToolManagement" element={<LLMToolManagement />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;