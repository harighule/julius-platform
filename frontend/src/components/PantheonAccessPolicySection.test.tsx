import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PantheonAccessPolicySection } from './PantheonAccessPolicySection'

describe('PantheonAccessPolicySection', () => {
  const samplePolicies = [
    { policy_key: 'pantheon.events.list', min_role: 'read_only', enabled: true, description: 'GET events' },
    { policy_key: 'pantheon.events.publish', min_role: 'operator', enabled: true, description: null },
  ]

  it('shows loading state', () => {
    render(
      <PantheonAccessPolicySection policies={[]} status="pending" canEdit={false} />,
    )
    expect(screen.getByTestId('pantheon-policy-loading')).toBeInTheDocument()
  })

  it('shows error state with message', () => {
    render(
      <PantheonAccessPolicySection
        policies={[]}
        status="error"
        errorMessage="503 Service Unavailable"
        canEdit={false}
      />,
    )
    expect(screen.getByTestId('pantheon-policy-error')).toHaveTextContent('503 Service Unavailable')
  })

  it('renders policy table rows when loaded', () => {
    render(
      <PantheonAccessPolicySection policies={samplePolicies} status="success" canEdit={false} />,
    )
    expect(screen.getByTestId('pantheon-policy-table')).toBeInTheDocument()
    expect(
      screen.getByTestId(`pantheon-policy-row-${encodeURIComponent('pantheon.events.list')}`),
    ).toBeInTheDocument()
    expect(screen.getByText('pantheon.events.list')).toBeInTheDocument()
    expect(screen.getByText('Policy edits require an admin or superadmin account.')).toBeInTheDocument()
  })

  it('shows empty message when no rows', () => {
    render(<PantheonAccessPolicySection policies={[]} status="success" canEdit={false} />)
    expect(screen.getByTestId('pantheon-policy-empty')).toBeInTheDocument()
  })

  it('allows admin to save a row', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <PantheonAccessPolicySection
        policies={samplePolicies}
        status="success"
        canEdit
        onSavePolicy={onSave}
      />,
    )
    const saves = screen.getAllByRole('button', { name: 'Save' })
    expect(saves.length).toBeGreaterThanOrEqual(1)
    await user.click(saves[0])
    expect(onSave).toHaveBeenCalledWith(
      'pantheon.events.list',
      expect.objectContaining({ min_role: 'read_only', enabled: true }),
    )
  })
})
