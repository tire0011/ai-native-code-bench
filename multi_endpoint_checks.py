"""Additional endpoint propagation checks; run after an arm has passed initial checks."""
from pathlib import Path
EXTRA = '''using Clean.Architecture.Web.Contributors;
using Clean.Architecture.UseCases.Contributors.Update;
namespace Clean.Architecture.UnitTests.Core.ContributorAggregate;
public class BenchEndpointPropagation
{
 private sealed class Captured : Exception { }
 [Theory][InlineData(" community ")][InlineData(null)]
 public async Task EndpointForwardsStatusAndCancellation(string? text)
 {
  var mediator=Substitute.For<IMediator>();
  using var source=new CancellationTokenSource(); var ct=source.Token;
  mediator.Send(Arg.Any<UpdateContributorCommand>(),ct).Returns(ValueTask.FromException<Ardalis.Result.Result<Clean.Architecture.UseCases.Contributors.ContributorDto>>(new Captured()));
  var endpoint=new Update(mediator);
  var req=new UpdateContributorRequest {Id=7,ContributorId=7,Name="Changed",Status=text};
  await Should.ThrowAsync<Captured>(async()=>await endpoint.ExecuteAsync(req,ct));
  await mediator.Received(1).Send(Arg.Is<UpdateContributorCommand>(c=>
   c.ContributorId==ContributorId.From(7) && c.NewName==ContributorName.From("Changed") &&
   (text==null ? c.NewStatus==null : ReferenceEquals(c.NewStatus,ContributorStatus.Community))),ct);
 }
 [Fact] public void GetMapperExposesActualStatus()
 {
  var dto=new Clean.Architecture.UseCases.Contributors.ContributorDto(ContributorId.From(1),ContributorName.From("Name"),PhoneNumber.Unknown,ContributorStatus.CoreTeam);
  new GetContributorByIdMapper().FromEntity(dto).Status.ShouldBe("CoreTeam");
 }
}
'''
