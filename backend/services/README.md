# Backend API Service

This directory contains TypeScript API services that interface with the Python FastAPI backend running on port 8001.

## Overview

The API service is structured into two main files:

- [`types.ts`](./types.ts) - Contains all TypeScript interfaces, types, and the core API client
- [`api.ts`](./api.ts) - Contains service wrappers with error handling and React hooks

## Features

### 1. Type Safety
All API endpoints have corresponding TypeScript interfaces that match the Pydantic models in the Python backend.

### 2. Error Handling
- Custom `ApiError` class for consistent error handling
- `handleApiError` function for error message extraction
- `withErrorHandling` wrapper for async operations

### 3. React Integration
- Pre-built React hooks for common operations
- State management with loading and error states
- Cleanup on component unmount

### 4. Service Organization
API endpoints are organized into logical services:
- `CustomerService` - Customer data and invoices
- `OnuService` - ONU device management
- `TicketService` - Ticket management system
- `CliService` - Terminal management
- `ConfigService` - Configuration management

## Usage Examples

### Basic API Calls

```typescript
import { ApiService } from './services/api';

// Get customer invoices
const getCustomerData = async (query: string) => {
  try {
    const customers = await ApiService.customer.getInvoices(query);
    console.log('Customer data:', customers);
  } catch (error) {
    console.error('API Error:', error.message);
  }
};

// Get ONU details
const getOnuDetails = async (oltName: string, interface: string) => {
  try {
    const details = await ApiService.onu.getCustomerDetails({
      olt_name: oltName,
      interface: interface
    });
    console.log('ONU details:', details);
  } catch (error) {
    console.error('API Error:', error.message);
  }
};
```

### Using Service Wrappers with Error Handling

```typescript
import { CustomerService, OnuService } from './services/api';

// With automatic error handling
const fetchCustomerData = async () => {
  const result = await CustomerService.getInvoices('customer-query');
  
  if (result.error) {
    console.error('Failed to fetch customer data:', result.error);
    return;
  }
  
  console.log('Customer data:', result.data);
};

// ONU operations
const rebootOnuDevice = async (oltName: string, interface: string) => {
  const result = await OnuService.rebootOnu({
    olt_name: oltName,
    interface: interface
  });
  
  if (result.error) {
    console.error('Failed to reboot ONU:', result.error);
    return;
  }
  
  console.log('Reboot status:', result.data?.status);
};
```

### Using React Hooks

```typescript
import React from 'react';
import { useCustomerData, useOnuDetails } from './services/api';

const CustomerComponent = ({ customerId }) => {
  const { data: customers, loading, error } = useCustomerData(customerId);
  
  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  
  return (
    <div>
      <h2>Customer Data</h2>
      {customers?.map(customer => (
        <div key={customer.id}>
          <p>Name: {customer.name}</p>
          <p>PPPoE User: {customer.user_pppoe}</p>
        </div>
      ))}
    </div>
  );
};

const OnuDetailsComponent = ({ oltName, interface }) => {
  const { data: onuDetails, loading, error } = useOnuDetails({ olt_name: oltName, interface });
  
  if (loading) return <div>Loading ONU details...</div>;
  if (error) return <div>Error: {error}</div>;
  
  return (
    <div>
      <h2>ONU Details</h2>
      <p>Serial Number: {onuDetails?.serial_number}</p>
      <p>Distance: {onuDetails?.onu_distance}</p>
      <p>Online Duration: {onuDetails?.online_duration}</p>
    </div>
  );
};
```

## API Endpoints Reference

### Customer Service
- `getPSBData()` - Get PSB data
- `getInvoices(query: string)` - Get customer invoices by query

### ONU Service
- `getCustomerDetails(payload)` - Get detailed ONU information
- `getOnuState(payload)` - Get ONU state
- `getOnuRx(payload)` - Get ONU RX power
- `rebootOnu(payload)` - Reboot ONU
- `removeOnu(payload)` - Remove ONU
- `registerSn(payload)` - Register new serial number

### Ticket Service
- `createOnly(payload)` - Create ticket only
- `createAndProcess(payload)` - Create and process ticket
- `processOnly(payload)` - Process existing ticket
- `close(payload)` - Close ticket
- `forward(payload)` - Forward ticket
- `search(payload)` - Search tickets

### CLI Service
- `startTerminal()` - Start new terminal session
- `stopTerminal(port: number)` - Stop terminal session
- `listRunningTerminals()` - List active terminals

### Config Service
- `getOptions()` - Get configuration options
- `detectUnconfiguredOnts(oltName: string)` - Detect unconfigured ONTs
- `runConfiguration(oltName: string, request)` - Run configuration

## Error Handling

The API service provides comprehensive error handling:

1. **Network Errors** - Handled automatically with retry suggestions
2. **API Errors** - Parsed from backend error responses
3. **Validation Errors** - Caught and formatted for display
4. **Timeout Errors** - Handled with appropriate messaging

## Configuration

The API base URL is configured in `types.ts`. By default, it points to `http://localhost:8001`.

To change the base URL, modify the `API_BASE_URL` constant in `types.ts`:

```typescript
const API_BASE_URL = 'https://your-api-domain.com';
```

## Development Notes

1. All API calls are typed and match the Python backend models
2. Error handling is consistent across all endpoints
3. React hooks provide state management out of the box
4. Service wrappers simplify common operations
5. The API client handles JSON serialization/deserialization automatically

## Dependencies

This API service requires:
- TypeScript
- React (for hooks usage)
- A running instance of the Python FastAPI backend

## Testing

To test the API service:

1. Ensure the Python backend is running on port 8001
2. Import and use the service in your React components
3. Check the browser console for any network errors
4. Verify the data structure matches the expected TypeScript interfaces