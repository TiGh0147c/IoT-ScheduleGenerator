<template>
  <div class="wb">
    <nav class="wb-rail" aria-label="模块">
      <router-link
        v-for="item in MODULES"
        :key="item.to"
        :to="item.to"
        class="wb-rail__btn"
        :class="{ 'is-on': isOn(item.to) }"
      >
        {{ item.short }}
      </router-link>
    </nav>
    <div class="wb-body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const MODULES = [
  { to: '/knowledge', short: '逻辑推理模板' },
  { to: '/treeview', short: '设备分类树' },
  { to: '/home', short: '配置环境' },
  { to: '/intent', short: '意图解析' },
] as const

const route = useRoute()

function isOn(path: string): boolean {
  return route.path === path
}
</script>
