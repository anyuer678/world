export interface JSONSchema {
  type?: string
  title?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  minimum?: number
  maximum?: number
  $ref?: string
  anyOf?: JSONSchema[]
  allOf?: JSONSchema[]
  properties?: Record<string, JSONSchema>
  $defs?: Record<string, JSONSchema>
  nullable?: boolean
}
