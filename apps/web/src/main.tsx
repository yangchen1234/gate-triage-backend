import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import YardPrototype from './YardPrototype';
import './styles.css';
const yardPreview = new URLSearchParams(window.location.search).get('preview') === 'yard';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{yardPreview ? <YardPrototype /> : <App />}</React.StrictMode>);
