import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { WeeklyData } from '@/lib/api'
import { formatDate } from '@/lib/utils'

interface WeeklyChartProps {
  data: WeeklyData[]
}

export function WeeklyChart({ data }: WeeklyChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    label: formatDate(d.date).split(',')[0],
    isShivangi: d.with_shivangi > 0,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Weekly Activity</CardTitle>
      </CardHeader>
      <CardContent className="h-[200px]">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            No data this week
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: '#9E8B7A' }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: '#9E8B7A' }}
                width={30}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#FDF8F3',
                  border: '1px solid #D4C4B5',
                  borderRadius: '8px',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
                }}
                labelStyle={{ color: '#3D2914', fontWeight: 'bold' }}
              />
              <Bar
                dataKey="total"
                fill="#8B7355"
                radius={[4, 4, 0, 0]}
                maxBarSize={40}
              />
              <Bar
                dataKey="with_shivangi"
                fill="#CD853F"
                radius={[4, 4, 0, 0]}
                maxBarSize={40}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
