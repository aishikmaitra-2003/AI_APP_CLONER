import React from 'react';
export default function AutoLayout({children}){
  return (
    <div style={{fontFamily:'Arial, sans-serif', padding:20}}>
      {children}
    </div>
  );
}
