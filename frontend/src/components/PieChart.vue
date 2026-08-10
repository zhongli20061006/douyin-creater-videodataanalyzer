<script setup lang="ts">
import { computed } from 'vue'
import { PieChart as EChartsPie } from 'echarts/charts'
import { LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

use([EChartsPie, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  title: string
  data: { name: string; value: number }[]
}>()

const option = computed(() => ({
  title: {
    text: props.title,
    left: 'center',
    textStyle: { color: 'var(--spider-text)', fontSize: 14 },
  },
  tooltip: { trigger: 'item' },
  legend: {
    bottom: 0,
    textStyle: { color: 'var(--spider-text-secondary)' },
  },
  series: [
    {
      type: 'pie',
      radius: ['40%', '68%'],
      center: ['50%', '46%'],
      itemStyle: { borderRadius: 6, borderColor: 'var(--spider-bg)', borderWidth: 2 },
      label: { color: 'var(--spider-text-secondary)', formatter: '{b}: {c}' },
      data: props.data,
    },
  ],
}))
</script>

<template>
  <v-chart :option="option" autoresize class="pie" />
</template>

<style scoped>
.pie {
  height: 300px;
  width: 100%;
}
</style>
