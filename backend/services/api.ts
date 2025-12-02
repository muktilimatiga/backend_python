import { useState, useEffect } from 'react';
import { ApiService, ApiError } from './types';

// Re-export the main API service for convenience
export { ApiService, ApiError };

// Helper function to handle API errors consistently
export const handleApiError = (error: unknown): string => {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
};

// Higher-order function for async operations with consistent error handling
export const withErrorHandling = async <T>(
  operation: () => Promise<T>
): Promise<{ data?: T; error?: string }> => {
  try {
    const data = await operation();
    return { data };
  } catch (error) {
    return { error: handleApiError(error) };
  }
};

// Specific service wrappers with enhanced error handling
export const CustomerService = {
  getPSBData: () => withErrorHandling(() => ApiService.customer.getPSBData()),
  getInvoices: (query: string) => withErrorHandling(() => ApiService.customer.getInvoices(query)),
};

export const OnuService = {
  getCustomerDetails: (payload: Parameters<typeof ApiService.onu.getCustomerDetails>[0]) =>
    withErrorHandling(() => ApiService.onu.getCustomerDetails(payload)),
  getOnuState: (payload: Parameters<typeof ApiService.onu.getOnuState>[0]) =>
    withErrorHandling(() => ApiService.onu.getOnuState(payload)),
  getOnuRx: (payload: Parameters<typeof ApiService.onu.getOnuRx>[0]) =>
    withErrorHandling(() => ApiService.onu.getOnuRx(payload)),
  rebootOnu: (payload: Parameters<typeof ApiService.onu.rebootOnu>[0]) =>
    withErrorHandling(() => ApiService.onu.rebootOnu(payload)),
  removeOnu: (payload: Parameters<typeof ApiService.onu.removeOnu>[0]) =>
    withErrorHandling(() => ApiService.onu.removeOnu(payload)),
  registerSn: (payload: Parameters<typeof ApiService.onu.registerSn>[0]) =>
    withErrorHandling(() => ApiService.onu.registerSn(payload)),
};

export const TicketService = {
  createOnly: (payload: Parameters<typeof ApiService.ticket.createOnly>[0]) =>
    withErrorHandling(() => ApiService.ticket.createOnly(payload)),
  createAndProcess: (payload: Parameters<typeof ApiService.ticket.createAndProcess>[0]) =>
    withErrorHandling(() => ApiService.ticket.createAndProcess(payload)),
  processOnly: (payload: Parameters<typeof ApiService.ticket.processOnly>[0]) =>
    withErrorHandling(() => ApiService.ticket.processOnly(payload)),
  close: (payload: Parameters<typeof ApiService.ticket.close>[0]) =>
    withErrorHandling(() => ApiService.ticket.close(payload)),
  forward: (payload: Parameters<typeof ApiService.ticket.forward>[0]) =>
    withErrorHandling(() => ApiService.ticket.forward(payload)),
  search: (payload: Parameters<typeof ApiService.ticket.search>[0]) =>
    withErrorHandling(() => ApiService.ticket.search(payload)),
};

export const CliService = {
  startTerminal: () => withErrorHandling(() => ApiService.cli.startTerminal()),
  stopTerminal: (port: number) => withErrorHandling(() => ApiService.cli.stopTerminal(port)),
  listRunningTerminals: () => withErrorHandling(() => ApiService.cli.listRunningTerminals()),
};

export const ConfigService = {
  getOptions: () => withErrorHandling(() => ApiService.config.getOptions()),
  detectUnconfiguredOnts: (oltName: string) => 
    withErrorHandling(() => ApiService.config.detectUnconfiguredOnts(oltName)),
  runConfiguration: (oltName: string, request: Parameters<typeof ApiService.config.runConfiguration>[1]) =>
    withErrorHandling(() => ApiService.config.runConfiguration(oltName, request)),
};

// React Query hooks for React integration (optional)
export const createQueryHook = <T, P extends any[]>(
  queryFn: (...args: P) => Promise<T>,
  options?: {
    onSuccess?: (data: T) => void;
    onError?: (error: string) => void;
  }
) => {
  return (...args: P) => {
    const [state, setState] = useState<{ data?: T; loading: boolean; error?: string }>({
      loading: true,
    });

    useEffect(() => {
      let isMounted = true;

      const fetchData = async () => {
        try {
          setState({ loading: true });
          const result = await withErrorHandling(() => queryFn(...args));
          
          if (!isMounted) return;
          
          if (result.error) {
            setState({ loading: false, error: result.error });
            options?.onError?.(result.error);
          } else {
            setState({ loading: false, data: result.data });
            options?.onSuccess?.(result.data);
          }
        } catch (error) {
          if (!isMounted) return;
          const errorMessage = handleApiError(error);
          setState({ loading: false, error: errorMessage });
          options?.onError?.(errorMessage);
        }
      };

      fetchData();

      return () => {
        isMounted = false;
      };
    }, args);

    return state;
  };
};

// React hooks for common operations
export const useCustomerData = createQueryHook(
  (query: string) => ApiService.customer.getInvoices(query)
);

export const useOnuDetails = createQueryHook(
  (payload: Parameters<typeof ApiService.onu.getCustomerDetails>[0]) => 
    ApiService.onu.getCustomerDetails(payload)
);

export const useTerminalList = createQueryHook(
  () => ApiService.cli.listRunningTerminals()
);

export const useConfigOptions = createQueryHook(
  () => ApiService.config.getOptions()
);