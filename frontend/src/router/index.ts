import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/intent',
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('../views/KnowledgeConfig.vue'),
    },
    {
      path: '/treeview',
      name: 'cap-tree',
      component: () => import('../views/CapTreeView.vue'),
    },
    {
      path: '/home',
      name: 'home-env',
      component: () => import('../views/HomeEnv.vue'),
    },
    {
      path: '/intent',
      name: 'intent-resolve',
      component: () => import('../views/IntentResolve.vue'),
    },
  ],
})

export default router
