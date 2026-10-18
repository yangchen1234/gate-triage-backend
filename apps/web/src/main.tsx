import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import YardPrototype from './YardPrototype';
import './styles.css';
const legacyView = new URLSearchParams(window.location.search).get('view') === 'legacy';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{legacyView ? <App /> : <YardPrototype />}</React.StrictMode>);
