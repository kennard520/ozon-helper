import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import './theme.css'
import './styles/tokens.css'
import './styles/element-theme.css'
import App from './App.vue'
import { router } from './router/index.js'
import { consumeUrlToken } from './auth.js'

consumeUrlToken()
createApp(App).use(createPinia()).use(ElementPlus).use(router).mount('#app')
