import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/assets/main.css'
import { Providers } from '@/app/providers'
import { ReportPage } from '@/components/report/ReportPage'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <ReportPage />
    </Providers>
  </React.StrictMode>,
)
