import React, { useState } from 'react';
import { 
  CustomerService, 
  OnuService, 
  TicketService, 
  ApiService,
  ApiError 
} from './api';
import { 
  OnuTargetPayload, 
  TicketCreateOnlyPayload,
  CustomerwithInvoices 
} from './types';

// Example component demonstrating API usage
export const ApiExampleComponent: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [customerData, setCustomerData] = useState<CustomerwithInvoices[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onuDetails, setOnuDetails] = useState<any>(null);

  // Function to search for customers
  const handleCustomerSearch = async () => {
    if (!searchQuery.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await CustomerService.getInvoices(searchQuery);
      if (result.error) {
        setError(result.error);
      } else {
        setCustomerData(result.data || []);
      }
    } catch (err) {
      setError('Failed to fetch customer data');
    } finally {
      setLoading(false);
    }
  };

  // Function to get ONU details
  const handleGetOnuDetails = async (oltName: string, interface: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const payload: OnuTargetPayload = {
        olt_name: oltName,
        interface: interface
      };
      
      const result = await OnuService.getCustomerDetails(payload);
      if (result.error) {
        setError(result.error);
      } else {
        setOnuDetails(result.data);
      }
    } catch (err) {
      setError('Failed to fetch ONU details');
    } finally {
      setLoading(false);
    }
  };

  // Function to create a ticket
  const handleCreateTicket = async (ticketData: TicketCreateOnlyPayload) => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await TicketService.createOnly(ticketData);
      if (result.error) {
        setError(result.error);
      } else {
        alert('Ticket created successfully!');
      }
    } catch (err) {
      setError('Failed to create ticket');
    } finally {
      setLoading(false);
    }
  };

  // Example of using the raw ApiService directly
  const handleDirectApiCall = async () => {
    try {
      const terminals = await ApiService.cli.listRunningTerminals();
      console.log('Running terminals:', terminals);
    } catch (err) {
      if (err instanceof ApiError) {
        console.error('API Error:', err.message, 'Status:', err.status);
      } else {
        console.error('Unknown error:', err);
      }
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h1>API Service Example</h1>
      
      {/* Customer Search Section */}
      <div style={{ marginBottom: '30px' }}>
        <h2>Customer Search</h2>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Enter customer query..."
            style={{ flex: 1, padding: '8px' }}
          />
          <button 
            onClick={handleCustomerSearch}
            disabled={loading}
            style={{ padding: '8px 16px' }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        
        {error && <div style={{ color: 'red', marginBottom: '10px' }}>Error: {error}</div>}
        
        {customerData && (
          <div>
            <h3>Results:</h3>
            {customerData.length === 0 ? (
              <p>No customers found</p>
            ) : (
              <ul>
                {customerData.map((customer) => (
                  <li key={customer.id}>
                    <strong>{customer.name}</strong> - {customer.user_pppoe}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* ONU Details Section */}
      <div style={{ marginBottom: '30px' }}>
        <h2>ONU Details</h2>
        <button 
          onClick={() => handleGetOnuDetails('OLT-SAMPLE', '1/2/3:4')}
          disabled={loading}
          style={{ padding: '8px 16px', marginBottom: '10px' }}
        >
          Get Sample ONU Details
        </button>
        
        {onuDetails && (
          <div style={{ border: '1px solid #ccc', padding: '10px', borderRadius: '4px' }}>
            <h3>ONU Information:</h3>
            <p><strong>Serial Number:</strong> {onuDetails.serial_number}</p>
            <p><strong>Distance:</strong> {onuDetails.onu_distance}</p>
            <p><strong>Online Duration:</strong> {onuDetails.online_duration}</p>
            <p><strong>IP Address:</strong> {onuDetails.ip_remote}</p>
          </div>
        )}
      </div>

      {/* Ticket Creation Section */}
      <div style={{ marginBottom: '30px' }}>
        <h2>Create Ticket</h2>
        <button 
          onClick={() => handleCreateTicket({
            query: 'Sample ticket query',
            description: 'This is a sample ticket created from the frontend',
            priority: 'MEDIUM',
            jenis: 'FREE'
          })}
          disabled={loading}
          style={{ padding: '8px 16px' }}
        >
          Create Sample Ticket
        </button>
      </div>

      {/* Direct API Call Section */}
      <div style={{ marginBottom: '30px' }}>
        <h2>Direct API Call</h2>
        <button 
          onClick={handleDirectApiCall}
          style={{ padding: '8px 16px' }}
        >
          List Running Terminals (check console)
        </button>
      </div>

      <div style={{ marginTop: '30px', padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
        <h3>Usage Notes:</h3>
        <ul>
          <li>All API calls are automatically wrapped with error handling</li>
          <li>Loading states are managed for better UX</li>
          <li>Check the browser console for detailed API responses</li>
          <li>Ensure the Python backend is running on localhost:8001</li>
          <li>See the README.md file for more detailed usage examples</li>
        </ul>
      </div>
    </div>
  );
};

// Export for use in your application
export default ApiExampleComponent;