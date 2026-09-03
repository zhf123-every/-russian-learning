export default function SentenceList({ sentences, curIdx, playingIdx, onPick }) {
  return (
    <div className="sent-list" style={{ maxHeight: 'none' }}>
      {sentences.map((s, i) => (
        <div key={s.id}
          className={'sent' + (i === curIdx ? ' active' : '') + (i === playingIdx ? ' playing' : '')}
          onClick={() => onPick(i)}>
          <span className="idx">{i + 1}</span>
          <span>{s.russian}</span>
        </div>
      ))}
    </div>
  )
}
