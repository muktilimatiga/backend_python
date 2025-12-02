// Base API configuration
const API_BASE_URL = 'http://localhost:8001';

// Generic API response wrapper
interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: number;
  success: boolean;
}

// Enhanced error handling for API responses
class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public response?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Customer-related types
export interface Customer {
  id: string;
  name?: string;
  user_pppoe?: string;
  detail_url: string;
}

export interface DataPSB {
  name?: string;
  address?: string;
  user_pppoe?: string;
  pppoe_password?: string;
  paket?: string;
}

export interface InvoiceItem {
  status?: string;
  package?: string;
  period?: string;
  month?: number;
  year?: number;
  payment_link?: string;
  description?: string;
}

export interface BillingSummary {
  this_month?: string;
  arrears_count: number;
  last_paid_month?: string;
}

export interface CustomerwithInvoices extends Customer {
  invoices?: BillingSummary[];
}

// ONU-related types
export interface OltBasePayload {
  olt_name: string;
}

export interface OnuTargetPayload extends OltBasePayload {
  interface: string;
}

export interface PortTargetPayload extends OltBasePayload {
  olt_port: string;
}

export interface RegistSnPayload extends OnuTargetPayload {
  sn: string;
}

export interface NoOnuPayload extends PortTargetPayload {
  onu_id: number;
}

export interface EthPortStatus {
  interface: string;
  is_unlocked: boolean;
}

export interface CustomerOnuDetail {
  type?: string;
  phase_state?: string;
  serial_number?: string;
  onu_distance?: string;
  online_duration?: string;
  modem_logs?: string;
  redaman: string;
  ip_remote: string;
  eth_port: EthPortStatus[];
}

export interface OnuStateResponse {
  onu_state_data: string;
}

export interface OnuRxResponse {
  onu_rx_data: string;
}

export interface RebootResponse {
  status: string;
}

export interface NoOnuResponse {
  status: string;
}

export interface RegistSnResponse {
  status: string;
}

// Ticket-related types
export interface TicketCreateOnlyPayload {
  query: string;
  description: string;
  priority?: string;
  jenis?: string;
}

export interface TicketCreateAndProcessPayload extends TicketCreateOnlyPayload {
  noc_username: string;
  noc_password: string;
}

export interface TicketProcessPayload {
  query: string;
  noc_username: string;
  noc_password: string;
}

export interface TicketClosePayload {
  query: string;
  close_reason: string;
  onu_sn: string;
  noc_username: string;
  noc_password: string;
}

export interface TicketForwardPayload {
  query: string;
  service_impact: string;
  root_cause: string;
  network_impact: string;
  recomended_action: string;
  onu_index: string;
  sn_modem: string;
  priority?: string;
  person_in_charge?: string;
  noc_username: string;
  noc_password: string;
}

export interface SearchPayload {
  query: string;
}

export interface TicketOperationResponse {
  success: boolean;
  message: string;
  creation_result?: string;
  processing_result?: string;
}

export interface SearchResponse {
  query: string;
  results: Record<string, any>[];
}

// CLI-related types
export interface TerminalResponse {
  port: number;
  pid: number;
  command: string;
  message: string;
}

export interface StopResponse {
  port: number;
  pid: number;
  message: string;
}

export interface ListResponse {
  count: number;
  running_ports: number[];
}

// Config-related types
export interface UnconfiguredOnt {
  sn: string;
  pon_port: string;
  pon_slot: string;
}

export interface CustomerInfo {
  name: string;
  address: string;
  pppoe_user: string;
  pppoe_pass: string;
}

export interface ConfigurationRequest {
  sn: string;
  customer: CustomerInfo;
  modem_type: string;
  package: string;
  eth_locks: boolean[];
}

export interface ConfigurationSummary {
  serial_number: string;
  pppoe_user: string;
  location: string;
  profile: string;
}

export interface ConfigurationResponse {
  message: string;
  summary?: ConfigurationSummary;
  logs: string[];
}

export interface OptionsResponse {
  olt_options: string[];
  modem_options: string[];
  package_options: string[];
}

export interface OnuLogEntry {
  id: number;
  auth_time: string;
  offline_time: string;
  cause: string;
}

export interface OnuDetail {
  onu_interface?: string;
  type?: string;
  phase_state?: string;
  serial_number?: string;
  onu_distance?: string;
  online_duration?: string;
  modem_logs: OnuLogEntry[];
}

// Enhanced fetch function with better error handling
async function fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  try {
    const url = `${API_BASE_URL}/api/v1${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      let errorMessage = `API Error: ${response.status} ${response.statusText}`;
      
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorMessage;
      } catch (e) {
        // If we can't parse the error as JSON, use the default message
      }
      
      throw new ApiError(errorMessage, response.status);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    
    console.error('Network or parsing error:', error);
    throw new ApiError('Network error or invalid response', 0);
  }
}

// API service object with all endpoints
export const ApiService = {
  // Customer endpoints
  customer: {
    getPSBData: (): Promise<DataPSB[]> => fetchJson<DataPSB[]>('/customer/psb'),
    getInvoices: (query: string): Promise<CustomerwithInvoices[]> => 
      fetchJson<CustomerwithInvoices[]>(`/customer/invoices?query=${encodeURIComponent(query)}`),
  },

  // ONU endpoints
  onu: {
    getCustomerDetails: (payload: OnuTargetPayload): Promise<CustomerOnuDetail> => 
      fetchJson<CustomerOnuDetail>('/onu/detail-search', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    getOnuState: (payload: PortTargetPayload): Promise<OnuStateResponse> => 
      fetchJson<OnuStateResponse>('/onu/onu-state', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    getOnuRx: (payload: PortTargetPayload): Promise<OnuRxResponse> => 
      fetchJson<OnuRxResponse>('/onu/onu-rx', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    rebootOnu: (payload: OnuTargetPayload): Promise<RebootResponse> => 
      fetchJson<RebootResponse>('/onu/reboot-onu', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    removeOnu: (payload: NoOnuPayload): Promise<NoOnuResponse> => 
      fetchJson<NoOnuResponse>('/onu/no-onu', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    registerSn: (payload: RegistSnPayload): Promise<RegistSnResponse> => 
      fetchJson<RegistSnResponse>('/onu/regist-sn', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },

  // Ticket endpoints
  ticket: {
    createOnly: (payload: TicketCreateOnlyPayload): Promise<TicketOperationResponse> => 
      fetchJson<TicketOperationResponse>('/ticket/create', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    createAndProcess: (payload: TicketCreateAndProcessPayload): Promise<TicketOperationResponse> => 
      fetchJson<TicketOperationResponse>('/ticket/create-and-process', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    processOnly: (payload: TicketProcessPayload): Promise<TicketOperationResponse> => 
      fetchJson<TicketOperationResponse>('/ticket/process', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    close: (payload: TicketClosePayload): Promise<TicketOperationResponse> => 
      fetchJson<TicketOperationResponse>('/ticket/close', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    forward: (payload: TicketForwardPayload): Promise<TicketOperationResponse> => 
      fetchJson<TicketOperationResponse>('/ticket/forward', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    search: (payload: SearchPayload): Promise<SearchResponse> => 
      fetchJson<SearchResponse>('/ticket/search', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },

  // CLI endpoints
  cli: {
    startTerminal: (): Promise<TerminalResponse> => 
      fetchJson<TerminalResponse>('/cli/start_terminal', {
        method: 'POST',
      }),
    stopTerminal: (port: number): Promise<StopResponse> => 
      fetchJson<StopResponse>(`/cli/stop_terminal/${port}`, {
        method: 'POST',
      }),
    listRunningTerminals: (): Promise<ListResponse> => 
      fetchJson<ListResponse>('/cli/running_terminals'),
  },

  // Config endpoints
  config: {
    getOptions: (): Promise<OptionsResponse> => 
      fetchJson<OptionsResponse>('/config/api/options'),
    detectUnconfiguredOnts: (oltName: string): Promise<UnconfiguredOnt[]> => 
      fetchJson<UnconfiguredOnt[]>(`/config/api/olts/${oltName}/detect-onts`),
    runConfiguration: (oltName: string, request: ConfigurationRequest): Promise<ConfigurationResponse> => 
      fetchJson<ConfigurationResponse>(`/config/api/olts/${oltName}/configure`, {
        method: 'POST',
        body: JSON.stringify(request),
      }),
  },
};

// Export the API error class for error handling
export { ApiError };