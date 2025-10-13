import React from 'react';

import DataAnalyst from "./data_analyst/data_analyst";
import Assistant from "./assistant/assistant";
import './App.css';
import {BrowserRouter, Route, Routes} from "react-router-dom";

function App() {
    return (
        <BrowserRouter basename="/web">
            <Routes>
                <Route path="/dataAnalyst" element={<DataAnalyst />} />
                <Route path="/assistant" element={<Assistant />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;