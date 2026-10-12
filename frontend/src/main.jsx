import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@mantine/core/styles.css'
import '@mantine/dropzone/styles.css'
import './index.css'
import App from './App.jsx'
import { MantineProvider, createTheme } from '@mantine/core'

const theme = createTheme({
  fontFamily: 'Instrument Sans, sans-serif',
  headings: { fontFamily: 'Instrument Sans, sans-serif' },
  primaryColor: 'blue',
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="light">
      <App />
    </MantineProvider>
  </StrictMode>,
)
