import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { initIosPwaDetection } from './iosPwa'
import { ConfirmProvider } from './ui/confirm'
import { ToastProvider } from './ui/toast'
import './styles/global.css'

initIosPwaDetection()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
)
