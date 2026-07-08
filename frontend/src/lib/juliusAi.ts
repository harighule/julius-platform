// Create this file: frontend/src/lib/juliusAi.ts

const API_BASE = 'http://localhost:8000';

export interface ScanResult {
  target: string;
  open_ports: number[];
  risk_assessment: Record<string, any>;
  recommendations: string[];
}

export interface ExploitResult {
  vulnerability: string;
  exploit_probability: number;
  breach_probability: number;
  exploit_chain: Array<{step: number; action: string; success_probability: number}>;
  recommendation: string;
}

export interface ThreatResult {
  threat: string;
  breach_probability: number;
  risk_level: string;
  recommended_action: string;
}

export interface CausalResult {
  cause: string;
  effect: string;
  strength: number;
  interpretation: string;
}

class JuliusAIService {
  private baseUrl: string = API_BASE;

  async getStatus(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/status`);
    return response.json();
  }

  async scan(target: string, ports?: number[]): Promise<ScanResult> {
    const response = await fetch(`${this.baseUrl}/api/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target, ports })
    });
    return response.json();
  }

  async exploit(vulnerability: string, target: string): Promise<ExploitResult> {
    const response = await fetch(`${this.baseUrl}/api/exploit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vulnerability, target })
    });
    return response.json();
  }

  async analyzeThreat(threatType: string): Promise<ThreatResult> {
    const response = await fetch(`${this.baseUrl}/api/threat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ threat_type: threatType })
    });
    return response.json();
  }

  async causalEffect(cause: string, effect: string): Promise<CausalResult> {
    const response = await fetch(`${this.baseUrl}/api/causal/${cause}/${effect}`);
    return response.json();
  }

  async causalChain(start: string, end: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/causal/chain/${start}/${end}`);
    return response.json();
  }
}

export const juliusAi = new JuliusAIService();