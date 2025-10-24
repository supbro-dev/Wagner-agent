import React from 'react';

import DataAnalyst from "./data_analyst/data_analyst";
import Assistant from "./assistant/assistant";
import AgentManagement from "./agent_management/agent_management";
import './App.css';
import {BrowserRouter, Route, Routes} from "react-router-dom";

function App() {
    return (
        <BrowserRouter basename="/web">
            <Routes>
                <Route path="/dataAnalyst" element={<DataAnalyst />} />
                <Route path="/assistant" element={<Assistant />} />
                <Route path="/agentManagement" element={<AgentManagement />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;