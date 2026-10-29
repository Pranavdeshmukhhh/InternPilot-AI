export const dynamic = 'force-static';
import { ImageResponse } from 'next/og';
export async function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          background: '#f7f7f3',
          color: '#20272d',
          padding: 80,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, fontSize: 30 }}>
          <div
            style={{
              display: 'flex',
              background: '#20272d',
              color: 'white',
              width: 52,
              height: 52,
              borderRadius: 18,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            IP
          </div>
          InternPilot AI
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          <div style={{ fontSize: 90, letterSpacing: -5, lineHeight: 1 }}>A clearer next step.</div>
          <div style={{ fontSize: 28, color: '#58636b' }}>
            Internships. Hackathons. A little more direction.
          </div>
        </div>
        <div style={{ display: 'flex', fontSize: 18, color: '#58636b' }}>
          Discover with context. Keep your applications in your control.
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
