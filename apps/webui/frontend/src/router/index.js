import { createRouter, createWebHashHistory } from 'vue-router'
import { isLoggedIn } from '../auth.js'
import AppLayout from '../layouts/AppLayout.vue'

const routes = [
  { path: '/login', name: 'login', meta: { public: true },
    component: () => import('../views/Login.vue') },
  { path: '/', component: AppLayout, children: [
    { path: '', name: 'drafts', component: () => import('../views/Workbench.vue') },
    { path: 'analytics', name: 'analytics', component: () => import('../views/Placeholder.vue') },
    { path: 'stores', name: 'stores', component: () => import('../views/Stores.vue') },
    { path: 'warehouses', name: 'warehouses', component: () => import('../views/Warehouses.vue') },
    { path: 'fulfillment', name: 'fulfillment', component: () => import('../views/Fulfillment.vue') },
    { path: 'settings', name: 'settings', component: () => import('../views/Settings.vue') },
    { path: 'users', name: 'users', component: () => import('../views/Users.vue') },
    { path: 'wallet', name: 'wallet', component: () => import('../views/Wallet.vue') },
  ] },
]
export const router = createRouter({ history: createWebHashHistory(), routes })
router.beforeEach((to) => {
  if (!to.meta.public && !isLoggedIn()) return { path: '/login' }
  if (to.path === '/login' && isLoggedIn()) return { path: '/' }
})
