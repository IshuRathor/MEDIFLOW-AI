import { createElement as h, useState } from 'react'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const axisMoney = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', notation: 'compact', maximumFractionDigits: 1 })
const colors = ['#18716b', '#a54835', '#514f97', '#765b17']

export const financePrompts = [
  'Show total revenue this month',
  'Show monthly collections for the last 12 months',
  'Compare revenue and expenses',
  'Which expense category costs us the most?',
  'Show outstanding payments',
  'Compare this month with last month',
  'Show quarterly financial performance',
  'Show our financial performance trend',
  'Identify unusual expenses',
  "Forecast next month's collections",
]

export function formatINR(value) {
  return inr.format(value)
}

function formatMetric(metric) {
  if (metric.value === null) return 'Unavailable'
  if (metric.unit === 'INR') return formatINR(metric.value)
  return metric.unit === 'percent' ? `${metric.value}%` : String(Number(metric.value))
}

function ChartTable({ chart }) {
  return h('div', { className: 'finance-table-scroll' },
    h('table', null,
      h('caption', null, chart.title),
      h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Period or category'),
        chart.series.map((series) => h('th', { scope: 'col', key: series.label }, series.label)))),
      h('tbody', null, chart.labels.map((label, index) => h('tr', { key: index },
        h('th', { scope: 'row' }, label),
        chart.series.map((series) => h('td', { key: series.label }, formatINR(series.values[index]))),
      ))),
    ),
  )
}

function FinanceChart({ chart }) {
  const [active, setActive] = useState(null)
  const width = 620
  const left = 68
  const right = width - 16
  const top = 16
  const bottom = 165
  const rowWidth = (right - left) / Math.max(chart.labels.length, 1)
  const values = chart.series.flatMap((series) => series.values.map(Number))
  const minimum = Math.min(0, ...values)
  const maximum = Math.max(0, ...values)
  const range = maximum - minimum || 1
  const x = (index) => left + (index + 0.5) * rowWidth
  const y = (amount) => bottom - ((amount - minimum) / range) * (bottom - top)
  const advance = Math.max(1, Math.ceil(chart.labels.length / 5))
  const ticks = [...new Set([minimum, (minimum + maximum) / 2, 0, maximum])].sort((a, b) => a - b)
  const tooltip = active && chart.series[active.series]?.values[active.index] !== undefined
    ? `${chart.labels[active.index]} · ${chart.series[active.series].label} · ${formatINR(chart.series[active.series].values[active.index])}`
    : null

  return h('article', { className: 'finance-chart' },
    h('h4', null, chart.title),
    chart.has_activity && chart.labels.length
      ? h('div', { className: 'finance-chart-scroll' }, h('svg', {
        viewBox: `0 0 ${width} 202`, 'aria-label': `${chart.title} in INR`,
      },
      ticks.map((tick) => h('g', { key: tick },
        h('line', { x1: left, x2: right, y1: y(tick), y2: y(tick), stroke: '#d0ccc4' }),
        h('text', { x: left - 6, y: y(tick) + 4, textAnchor: 'end' }, axisMoney.format(tick)),
      )),
      chart.labels.map((label, index) => index % advance === 0 && h('text', {
        key: index, x: x(index), y: bottom + 20, textAnchor: 'middle',
      }, label.length > 18 ? `${label.slice(0, 16)}…` : label)),
      chart.series.map((series, seriesIndex) => {
        const color = colors[seriesIndex]
        const barWidth = Math.min(32, rowWidth * 0.78 / chart.series.length)
        return h('g', { key: series.label },
          chart.kind === 'line' && h('polyline', {
            points: series.values.map((amount, index) => `${x(index)},${y(Number(amount))}`).join(' '),
            fill: 'none', stroke: color, strokeWidth: 2,
          }),
          series.values.map((amount, index) => {
            const cy = y(Number(amount))
            const description = `${chart.labels[index]}, ${series.label}: ${formatINR(amount)}`
            const activate = () => setActive({ series: seriesIndex, index })
            return h('g', {
              key: index, tabIndex: 0, 'aria-label': description, onMouseEnter: activate, onFocus: activate,
            },
            h('title', null, description),
            chart.kind === 'line'
              ? h('circle', { cx: x(index), cy, r: 4, fill: color })
              : h('rect', {
                x: x(index) + (seriesIndex - chart.series.length / 2) * barWidth,
                y: Math.min(cy, y(0)), width: Math.max(1, barWidth - 2),
                height: Math.max(2, Math.abs(cy - y(0))), fill: color,
              }),
            )
          }),
        )
      })))
      : h('p', null, 'No records in this range.'),
    chart.has_activity && h('ul', { className: 'finance-legend' }, chart.series.map((series, index) => h('li', {
      key: series.label,
    }, h('span', { style: { backgroundColor: colors[index] }, 'aria-hidden': true }), series.label))),
    tooltip && h('output', { 'aria-live': 'polite' }, tooltip),
    chart.labels.length > 0 && h('details', null, h('summary', null, 'View data table'), h(ChartTable, { chart })),
  )
}

export default function FinanceReport({ report }) {
  if (!report) return null
  const period = report.start_date ? `${report.start_date} to ${report.end_date}` : `As of ${report.end_date}`
  return h('section', { className: 'finance-report', 'aria-label': report.title },
    h('p', null, `${period} · ${report.timezone} · ${report.currency}`),
    report.metrics.length > 0 && h('dl', { className: 'finance-metrics' }, report.metrics.map((metric, index) =>
      h('div', { key: index }, h('dt', null, metric.label), h('dd', null, formatMetric(metric))))),
    report.charts.map((chart) => h(FinanceChart, { key: chart.title, chart })),
    report.notes.length > 0 && h('ul', { className: 'finance-notes' }, report.notes.map((note) => h('li', { key: note }, note))),
  )
}
