import React from 'react';

import Conversation from "./conversation/conversation";
import './App.css';
import {BrowserRouter, Route, Routes} from "react-router-dom";

function App() {
    return (
        <BrowserRouter basename="/web">
            <Routes>
                <Route path="/conversation" element={<Conversation />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;