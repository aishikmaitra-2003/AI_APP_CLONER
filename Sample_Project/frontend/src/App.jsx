import React, {useEffect, useState} from 'react';
import AutoLayout from './components/AutoLayout.jsx';

export default function App(){
  const [data, setData] = useState(null);
  useEffect(()=>{
    fetch('/api/data')
      .then(r=>r.json())
      .then(setData)
      .catch(e=>setData({error: String(e)}));
  }, []);
  return (
    <AutoLayout>
      <h1>Generated React Frontend</h1>
      <p>This is a functional fallback application. If the LLM generation was successful, this content should be replaced by the design extracted from the UX spec.</p>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </AutoLayout>
  );
}
