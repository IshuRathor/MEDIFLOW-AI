import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

export type DirectoryLookup<T> = { records: T[]; loading: boolean; error: string }

export default function DirectoryAutocomplete<T extends { id: number }>({
  label, value, lookup, selectedId, describe, noResults, onChange, onSelect,
}: {
  label: string
  value: string
  lookup: DirectoryLookup<T>
  selectedId?: number
  describe: (record: T) => string
  noResults: string
  onChange: (value: string) => void
  onSelect: (record: T) => void
}) {
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(-1)
  const expanded = open && !!value.trim()
  const records = lookup.loading || lookup.error ? [] : lookup.records
  const activeIndex = expanded && index < records.length ? index : -1

  useEffect(() => {
    if (!expanded) return
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [expanded])

  useEffect(() => {
    if (activeIndex >= 0) list.current?.children[activeIndex]?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  function choose(record: T) {
    onSelect(record)
    setOpen(false)
    setIndex(-1)
  }

  function navigate(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    switch (event.key) {
      case 'Escape':
        if (expanded) {
          event.preventDefault()
          event.stopPropagation()
          setOpen(false)
        }
        return
      case 'ArrowDown':
      case 'ArrowUp': {
        if (!value.trim()) return
        event.preventDefault()
        setOpen(true)
        const last = records.length - 1
        if (last < 0) return
        const down = event.key === 'ArrowDown'
        setIndex(activeIndex < 0 ? down ? 0 : last : Math.max(0, Math.min(last, activeIndex + (down ? 1 : -1))))
        return
      }
      case 'Enter':
        if (!expanded) return
        event.preventDefault()
        if (activeIndex >= 0) choose(records[activeIndex])
    }
  }

  return <div ref={root} className="booking-autocomplete" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }}>
    <label htmlFor={id}>{label}</label>
    <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={expanded}
      aria-controls={expanded ? `${id}-results` : undefined}
      aria-activedescendant={activeIndex >= 0 ? `${id}-option-${records[activeIndex].id}` : undefined}
      autoComplete="off" maxLength={120} value={value}
      onFocus={() => { setOpen(true); setIndex(-1) }}
      onChange={(event) => { onChange(event.target.value); setOpen(true); setIndex(-1) }}
      onKeyDown={navigate} />
    {expanded && <div className="booking-suggestions">
      {lookup.loading && <p role="status">Loading matches…</p>}
      {lookup.error && <p className="form-error" role="alert">{lookup.error}</p>}
      {!lookup.loading && !lookup.error && !records.length && <p role="status">{noResults}</p>}
      <ul id={`${id}-results`} ref={list} role="listbox" aria-label={`${label} matches`}>
        {records.map((record, position) => <li key={record.id} id={`${id}-option-${record.id}`} role="option"
          aria-selected={record.id === selectedId} data-active={position === activeIndex}
          onMouseDown={(event) => event.preventDefault()} onClick={() => choose(record)}>{describe(record)}</li>)}
      </ul>
    </div>}
  </div>
}
