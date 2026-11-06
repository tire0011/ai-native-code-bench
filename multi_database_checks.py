"""Persistence audit for changed DTO query producers; no external database needed."""
EXTRA = '''using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Clean.Architecture.Infrastructure.Data;
using Clean.Architecture.Infrastructure.Data.Queries;
namespace Clean.Architecture.UnitTests.Core.ContributorAggregate;
public class BenchStatusPersistence
{
 [Fact] public async Task ListPreservesStoredStatusAndPagination()
 {
  await using var connection=new SqliteConnection("Data Source=:memory:");
  await connection.OpenAsync(TestContext.Current.CancellationToken);
  var options=new DbContextOptionsBuilder<AppDbContext>().UseSqlite(connection).Options;
  await using var db=new AppDbContext(options); await db.Database.EnsureCreatedAsync(TestContext.Current.CancellationToken);
  for(int i=0;i<5;i++)
  {
   var c=new Contributor(ContributorName.From("Name"+i));
   c.UpdatePhoneNumber(new PhoneNumber("49","123"+i,null));
   c.UpdateStatus(i%2==0?ContributorStatus.Community:ContributorStatus.CoreTeam);
   typeof(Contributor).GetProperty("Id")!.SetValue(c,ContributorId.From(i+1));
   db.Contributors.Add(c);
  }
  await db.SaveChangesAsync(TestContext.Current.CancellationToken); db.ChangeTracker.Clear();
  var service=new ListContributorsQueryService(db);
  var page=await service.ListAsync(1,2);
  page.TotalCount.ShouldBe(5);page.TotalPages.ShouldBe(3);page.Items.Count.ShouldBe(2);
  page.Items[0].Status.Name.ShouldBe("Community");page.Items[1].Status.Name.ShouldBe("CoreTeam");
  var last=await service.ListAsync(3,2);
  last.TotalCount.ShouldBe(5);last.TotalPages.ShouldBe(3);last.Items.Count.ShouldBe(1);
  last.Items[0].Status.Name.ShouldBe("Community");
 }
}
'''
