import { useEffect, useState } from 'react'
import type { JSONSchema } from './schema'

interface FieldProps {
  root: JSONSchema
  schema: JSONSchema
  label: string
  value: unknown
  onChange: (v: unknown) => void
}

export function parseArrayText(text: string, itemType: string | undefined): unknown[] | null {
  const t = text.trim()
  if (t === '') return null
  if (itemType === 'integer' || itemType === 'number') {
    const parts = t.split(/[,\s;]+/).filter(Boolean)
    if (parts.length === 0) return null
    const nums = parts.map((p) => {
      const n = Number(p)
      if (!Number.isFinite(n)) return NaN
      return itemType === 'integer' && !Number.isInteger(n) ? NaN : n
    })
    if (nums.some((n) => !Number.isFinite(n))) return null
    return nums
  }
  try {
    const v = JSON.parse(t)
    return Array.isArray(v) ? v : null
  } catch {
    return null
  }
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function ArrayField({ root, schema, label, value, onChange }: FieldProps) {
  const s = resolve(root, schema)
  const itemType = s.items?.type
  const numeric = itemType === 'integer' || itemType === 'number'
  const toText = (v: unknown) => (Array.isArray(v) ? (numeric ? (v as unknown[]).join(',') : JSON.stringify(v)) : '')
  const [text, setText] = useState(() => toText(value))
  const [invalid, setInvalid] = useState(false)
  useEffect(() => {
    setText((prev) => (sameJson(parseArrayText(prev, itemType), value) ? prev : toText(value)))
  }, [value, itemType])

  return (
    <label style={row}>
      <span style={labelStyle}>
        {label}
        {s.description ? <small style={hint}>{s.description}</small> : null}
        {invalid ? (
          <small style={invalidHint}>
            {numeric ? '无法解析为整数列表：请用逗号或空格分隔，如 1,2,3' : '需为合法 JSON 数组，如 [1,2,3]'}
          </small>
        ) : null}
      </span>
      <input
        type="text"
        value={text}
        onChange={(e) => {
          const raw = e.target.value
          setText(raw)
          if (raw.trim() === '') {
            setInvalid(false)
            onChange(s.nullable ? null : undefined)
            return
          }
          const parsed = parseArrayText(raw, itemType)
          if (parsed === null) {
            setInvalid(true)
            return
          }
          setInvalid(false)
          onChange(parsed)
        }}
        style={control}
      />
    </label>
  )
}

export function resolve(root: JSONSchema, s: JSONSchema): JSONSchema {
  if (s.$ref) {
    const name = s.$ref.replace('#/$defs/', '')
    const def = root.$defs?.[name]
    if (def) return def
  }
  if (s.allOf && s.allOf.length > 0) return resolve(root, s.allOf[0])
  if (s.anyOf) {
    const nonNull = s.anyOf.find((x) => x.type !== 'null')
    if (nonNull) {
      const inner = resolve(root, nonNull)
      return {
        ...inner,
        nullable: s.anyOf.some((x) => x.type === 'null'),
        title: s.title ?? inner.title,
        description: s.description ?? inner.description,
      }
    }
  }
  return s
}

function SchemaField({ root, schema, label, value, onChange }: FieldProps) {
  const s = resolve(root, schema)

  if (s.type === 'object' || s.properties) {
    return (
      <fieldset style={fieldset}>
        <legend>{label}</legend>
        {Object.entries(s.properties ?? {}).map(([k, v]) => (
          <SchemaField
            key={k}
            root={root}
            schema={v as JSONSchema}
            label={(v as JSONSchema).title ?? k}
            value={(value as Record<string, unknown> | null | undefined)?.[k] ?? (v as JSONSchema).default}
            onChange={(nv) => onChange({ ...(value as Record<string, unknown> | undefined), [k]: nv })}
          />
        ))}
      </fieldset>
    )
  }

  const numValue = value === null || value === undefined ? '' : String(value)

  if (s.enum) {
    return (
      <label style={row}>
        <span style={labelStyle}>{label}</span>
        <select value={numValue} onChange={(e) => onChange(e.target.value)} style={control}>
          {s.enum.map((opt) => (
            <option key={String(opt)} value={String(opt)}>
              {String(opt)}
            </option>
          ))}
        </select>
      </label>
    )
  }

  if (s.type === 'integer' || s.type === 'number') {
    return (
      <label style={row}>
        <span style={labelStyle}>
          {label}
          {s.description ? <small style={hint}>{s.description}</small> : null}
        </span>
        <input
          type="number"
          value={numValue}
          min={s.minimum}
          max={s.maximum}
          step={s.type === 'integer' ? 1 : 'any'}
          onChange={(e) => {
            const raw = e.target.value
            if (raw === '') {
              onChange(s.nullable ? null : undefined)
              return
            }
            const n = s.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw)
            onChange(Number.isNaN(n) ? undefined : n)
          }}
          style={control}
        />
      </label>
    )
  }

  if (s.type === 'boolean') {
    return (
      <label style={row}>
        <span style={labelStyle}>{label}</span>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
      </label>
    )
  }

  if (s.type === 'array') {
    return <ArrayField root={root} schema={schema} label={label} value={value} onChange={onChange} />
  }

  return (
    <label style={row}>
      <span style={labelStyle}>{label}</span>
      <input type="text" value={numValue} onChange={(e) => onChange(e.target.value)} style={control} />
    </label>
  )
}

export default function ParamForm({
  schema,
  value,
  onChange,
}: {
  schema: JSONSchema
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}) {
  const props = schema.properties ?? {}
  if (Object.keys(props).length === 0) return <p style={{ color: '#6b7280' }}>该模型没有可配置参数。</p>
  return (
    <div>
      {Object.entries(props).map(([k, v]) => (
        <SchemaField
          key={k}
          root={schema}
          schema={v as JSONSchema}
          label={(v as JSONSchema).title ?? k}
          value={value[k] ?? (v as JSONSchema).default}
          onChange={(nv) => onChange({ ...value, [k]: nv })}
        />
      ))}
    </div>
  )
}

const row: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }
const labelStyle: React.CSSProperties = { minWidth: 130, fontSize: 13, display: 'inline-flex', flexDirection: 'column' }
const hint: React.CSSProperties = { color: '#6b7280', fontSize: 11 }
const invalidHint: React.CSSProperties = { color: '#dc2626', fontSize: 11 }
const control: React.CSSProperties = { flex: 1, padding: 6, border: '1px solid #d1d5db', borderRadius: 6 }
const fieldset: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 6,
  margin: '6px 0',
  padding: '4px 10px 10px',
}
